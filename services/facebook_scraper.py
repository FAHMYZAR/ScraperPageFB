from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import re

from bs4 import BeautifulSoup

import CLI_Mode.facebook_reels_cli as fb_cli
from CLI_Mode.facebook_reels_cli import normalize_scan_order, safe_int
from models import CdnResult, CdnVariant, PageInfo, Reel, SessionStatus
from services.facebook_url_resolver import FacebookUrlResolver
from services.session_manager import SessionManager
from utils.cache import TTLCache
from utils.performance import clamp_concurrency, paginate


class FacebookScraper:
    def __init__(
        self,
        session_manager: SessionManager,
        default_target: str,
        workers: int = 4,
        cache: Optional[TTLCache[str, Any]] = None,
    ) -> None:
        self.session_manager = session_manager
        self.default_target = default_target
        self.workers = clamp_concurrency(workers, hard_limit=8)
        self.engine = fb_cli.ReelsScraper(session_manager.store, target=default_target, workers=self.workers)
        self.cache = cache or TTLCache[str, Any](ttl_seconds=300, max_items=32)
        self.resolver = FacebookUrlResolver()

    def _cache_key(self, prefix: str, *parts: Any) -> str:
        return "|".join([prefix, *[str(part) for part in parts]])

    def _extract_page_title(self, html: str, default: str = "") -> str:
        soup = BeautifulSoup(html, "html.parser")
        for selector in ('meta[property="og:title"]', 'meta[name="title"]', 'meta[property="twitter:title"]'):
            tag = soup.select_one(selector)
            if tag and tag.get("content"):
                return str(tag.get("content")).strip()
        if soup.title and soup.title.string:
            return str(soup.title.string).strip()
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(" ", strip=True)
        return default

    def _sort_cards(self, cards: List[Dict[str, Any]], order: str) -> List[Dict[str, Any]]:
        order_key = normalize_scan_order(order)
        if order_key == "oldest":
            return list(reversed(cards))
        return cards

    def _sort_reels(self, reels: List[Reel], order: str) -> List[Reel]:
        order_key = normalize_scan_order(order)
        if order_key != "popular":
            return [replace(reel, scan_index=index + 1) for index, reel in enumerate(reels)]
        sorted_reels = sorted(
            reels,
            key=lambda reel: (
                reel.views or 0,
                reel.likes or 0,
                reel.comments or 0,
                reel.shares or 0,
            ),
            reverse=True,
        )
        return [replace(reel, scan_index=index + 1) for index, reel in enumerate(sorted_reels)]

    def _collect_cards_sync(self, page_url: str, use_browser_scroll: bool = True) -> List[Dict[str, Any]]:
        cache_key = self._cache_key("cards", page_url, use_browser_scroll)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        cards = self.engine._collect_cards(page_url, use_browser_scroll=use_browser_scroll)
        self.cache.set(cache_key, cards)
        return cards

    def _fetch_summaries_sync(self, cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        max_workers = min(self.workers, len(cards) or 1)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.engine.fetch_reel_summary, card): card for card in cards}
            for future in futures:
                card = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "index": card.get("index", 0),
                        "reel_id": card.get("reel_id", ""),
                        "url": card.get("url", ""),
                        "card_views": card.get("card_views", ""),
                        "card_views_value": card.get("card_views_value", 0),
                        "status": "error",
                        "error": str(exc),
                    }
                result.setdefault("card_views_value", card.get("card_views_value", 0))
                results.append(result)
        results.sort(key=lambda item: item.get("index", 0) or 0)
        return results

    def _extract_cdn_variants(self, detail: Dict[str, Any]) -> tuple[List[CdnVariant], List[CdnVariant]]:
        variants = [CdnVariant.from_rendition(item) for item in list(detail.get("renditions", []) or [])]
        video_variants = [item for item in variants if item.url and not item.is_audio_only]
        audio_variants = [item for item in variants if item.url and item.is_audio_only]
        direct_url = str(detail.get("best_cdn_url", "") or "")
        if direct_url and not any(item.url == direct_url for item in video_variants):
            video_variants.append(
                CdnVariant(
                    url=direct_url,
                    quality=str(detail.get("best_cdn_quality", "") or "") or None,
                    bitrate=int(detail.get("best_cdn_bandwidth", 0) or 0) or None,
                    mime_type="video/mp4",
                    has_audio=not audio_variants,
                    is_audio_only=False,
                )
            )
        return video_variants, audio_variants

    def _choose_best_video(self, variants: List[CdnVariant]) -> Optional[CdnVariant]:
        if not variants:
            return None
        return sorted(variants, key=lambda item: (item.height or 0, item.width or 0, item.bitrate or 0), reverse=True)[0]

    def _choose_best_audio(self, variants: List[CdnVariant]) -> Optional[CdnVariant]:
        if not variants:
            return None
        return sorted(variants, key=lambda item: item.bitrate or 0, reverse=True)[0]

    def _extract_cdn(self, detail: Dict[str, Any]) -> CdnResult:
        video_variants, audio_variants = self._extract_cdn_variants(detail)
        best_video = self._choose_best_video(video_variants)
        best_audio = self._choose_best_audio(audio_variants)
        return CdnResult(
            video_url=best_video.url if best_video else (str(detail.get("best_cdn_url", "") or "") or None),
            audio_url=best_audio.url if best_audio else None,
            merged_audio_video_url=(best_video.url if best_video and best_video.has_audio else None),
            quality=(best_video.quality if best_video else str(detail.get("best_cdn_quality", "") or "") or None),
            title=str(detail.get("title", "") or ""),
            description=str(detail.get("description", "") or ""),
            reel_id=str(detail.get("reel_id", "") or ""),
            source_url=str(detail.get("url", "") or ""),
            thumbnail_url=str(detail.get("thumbnail_url", "") or ""),
            best_bandwidth=int(detail.get("best_cdn_bandwidth", 0) or 0),
            renditions=list(detail.get("renditions", []) or []),
            video_variants=video_variants,
            audio_variants=audio_variants,
            best_video=best_video,
            best_audio=best_audio,
            status=str(detail.get("status", "ok") or "ok"),
        )

    def _resolve_reel_reference(self, reel_ref: str, source_url: Optional[str] = None) -> Tuple[str, Optional[str]]:
        raw = str(reel_ref or "").strip()
        if raw.startswith("http") and "fbcdn.net" in raw:
            return raw, raw
        match = re.search(r"/reel/(\d+)", raw)
        if match:
            return match.group(1), source_url or raw
        video_match = re.search(r"[?&]v=(\d+)|/videos/(\d+)", raw)
        if video_match:
            return next(group for group in video_match.groups() if group), source_url or raw
        if raw.isdigit():
            return raw, source_url
        return raw, source_url or raw

    async def validate_session(self, target_url: Optional[str] = None) -> SessionStatus:
        target = target_url or self.default_target

        def _probe() -> SessionStatus:
            response = self.engine._request(target)
            usable = not self.engine._looks_like_login_form(response.text, response.url)
            cards = self.engine._extract_cards(response.text) if usable else []
            account_name = str(self.session_manager.account_name or "")
            account_id = str(self.session_manager.account_id or "")
            if usable and not account_name:
                identity = self.engine.resolve_account_identity()
                account_name = identity.get("name", account_name)
                account_id = identity.get("id", account_id)
                if account_name:
                    self.session_manager.store.meta["account_name"] = account_name
                    self.session_manager.store.meta["account_id"] = account_id
                    if identity.get("url"):
                        self.session_manager.store.meta["account_url"] = identity["url"]
                    self.session_manager.store.save()
            return self.session_manager.status_snapshot(
                valid=usable,
                reel_count=len(cards),
                last_checked_at=fb_cli.now_stamp(),
            )

        return await asyncio.to_thread(_probe)

    async def fetch_page_info(self, page_url: str) -> PageInfo:
        cache_key = self._cache_key("page_info", page_url)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        def _load() -> PageInfo:
            response = self.engine._request(page_url)
            cards = self.engine._collect_cards(page_url, use_browser_scroll=True)
            title = self._extract_page_title(response.text, default=page_url)
            name = title.replace(" | Facebook", "").replace("Facebook", "").strip()
            return PageInfo(
                name=name,
                title=title,
                url=response.url or page_url,
                total_items=len(cards),
                total_reels=len(cards),
                detected_cards=len(cards),
                source=page_url,
                description=name,
            )

        info = await asyncio.to_thread(_load)
        self.cache.set(cache_key, info)
        return info

    async def fetch_reels(
        self,
        page_url: str,
        order: str = "newest",
        max_reels: Optional[int] = None,
        use_browser_scroll: bool = True,
    ) -> List[Reel]:
        cache_key = self._cache_key("reels", page_url, order, max_reels, use_browser_scroll)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        def _load() -> List[Reel]:
            cards = self._collect_cards_sync(page_url, use_browser_scroll=use_browser_scroll)
            ordered_cards = self._sort_cards([dict(card) for card in cards], order)
            if max_reels is not None and max_reels > 0:
                ordered_cards = ordered_cards[:max_reels]
            summaries = self._fetch_summaries_sync(ordered_cards)
            reels = [Reel.from_summary({**summary, "scan_index": idx + 1}) for idx, summary in enumerate(summaries)]
            return self._sort_reels(reels, order)

        reels = await asyncio.to_thread(_load)
        self.cache.set(cache_key, reels)
        return reels

    async def fetch_popular_reels(
        self,
        page_url: str,
        page: int = 1,
        page_size: int = 3,
    ) -> tuple[List[Reel], int, int]:
        reels = await self.fetch_reels(page_url, order="popular", max_reels=None, use_browser_scroll=True)
        return paginate(reels, page, page_size)

    async def fetch_reel_detail(self, reel_ref: str, source_url: Optional[str] = None) -> CdnResult:
        url_ref, resolved_source = self._resolve_reel_reference(reel_ref, source_url)

        if url_ref.startswith("http") and "fbcdn.net" in url_ref:
            return CdnResult(
                video_url=url_ref,
                merged_audio_video_url=url_ref,
                quality="direct",
                title="",
                description="",
                reel_id=str(reel_ref),
                source_url=resolved_source or url_ref,
                status="ok",
            )

        def _load() -> CdnResult:
            detail = self.engine.fetch_reel_detail(url_ref, source_url=resolved_source)
            return self._extract_cdn(detail)

        return await asyncio.to_thread(_load)

    async def resolve_cdn(self, reel_ref: str, source_url: Optional[str] = None) -> CdnResult:
        normalized = reel_ref
        try:
            if self.resolver.is_facebook_video_url(reel_ref):
                normalized = await self.resolver.resolve_share_url(reel_ref)
        except Exception:
            normalized = reel_ref
        return await self.fetch_reel_detail(normalized, source_url=source_url)
