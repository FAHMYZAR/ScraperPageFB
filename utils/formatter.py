from __future__ import annotations

from html import escape
from datetime import datetime
from typing import Iterable, List, Sequence

from CLI_Mode.facebook_reels_cli import format_metric
from models import CdnResult, PageInfo, Reel, SessionStatus
from utils.performance import chunk_text


class Formatter:
    def greeting(self, user_name: str, now: datetime | None = None) -> str:
        current = now or datetime.now()
        hour = current.hour
        if hour < 11:
            greeting = "Selamat Pagi"
        elif hour < 15:
            greeting = "Selamat Siang"
        elif hour < 18:
            greeting = "Selamat Sore"
        else:
            greeting = "Selamat Malam"
        display_name = user_name or "User"
        return f"{greeting}, {display_name}"

    def loading_text(self, stage: str = "Loading", final: bool = False) -> str:
        bar = "▰▰▰▰▱" if not final else "▰▰▰▰▰"
        suffix = "Almost ready..." if not final else "Selesai."
        return f"🎮 {stage}\n{bar} {suffix}"

    def home_menu_text(self, user_name: str) -> str:
        safe_name = escape(user_name or "User")
        return (
            f"{self.greeting(safe_name)}\n\n"
            "Pilih menu di bawah ini:"
        )

    def session_status_text(self, status: SessionStatus, storage_id: str = "") -> str:
        valid_text = "usable" if status.valid is True else "expired" if status.valid is False else "missing"
        account = status.account_name or "-"
        if status.account_id:
            masked = status.account_id[:3] + "***" + status.account_id[-2:] if len(status.account_id) > 5 else "***"
            account = f"{account} ({masked})"

        parts = [
            "SESSION STATUS",
            "",
            f"Session test : {valid_text}",
            f"Session file : {storage_id or '-'}",
            f"Cookies      : {status.cookie_count}",
            f"Source       : {status.source or 'unknown'}",
            f"Account      : {account}",
            f"Saved        : {bool(status.available)}",
        ]
        parts.append(f"Last checked : {status.last_checked_at or '-'}")
        if status.error:
            parts.append(f"Error        : {status.error}")
        return "\n".join(parts)

    def page_info_text(self, page: PageInfo, session_status: str = "-") -> str:
        return (
            "🕷 Page Info\n\n"
            f"Nama page                 : {page.name or '-'}\n"
            f"Header/title page         : {page.title or '-'}\n"
            f"URL page                  : {page.url or page.source or '-'}\n"
            f"Total reel cards detected : {page.detected_cards or page.total_items}\n"
            f"Total reels diproses      : {page.total_reels}\n"
            f"Status session            : {session_status}"
        )

    def reel_card_line(self, reel: Reel) -> str:
        return (
            f"{reel.scan_index or 0}. {reel.title or reel.id}\n"
            f"👁 Views: {format_metric(reel.views, reel.card_views_text)}\n"
            f"❤️ Likes: {format_metric(reel.likes)}\n"
            f"💬 Comments: {format_metric(reel.comments)}\n"
            f"🔁 Shares: {format_metric(reel.shares)}\n"
            f"🎞 Best CDN: {reel.best_cdn_quality or '-'}"
        )

    def reel_list_text(
        self,
        reels: Sequence[Reel],
        page: int,
        total_pages: int,
        mode: str,
        selected_slots: Sequence[int] | None = None,
    ) -> str:
        mode_label = {
            "popular": "Popular",
            "pick": "Pick Sendiri",
            "newest": "Terbaru",
            "oldest": "Dari Bawah / Lama",
        }.get(mode, mode)
        emoji = "🔥" if mode == "popular" else "🆕" if mode == "newest" else "📜" if mode == "oldest" else "🎯"
        header = f"{emoji} {mode_label} Reels\nPage {page}/{total_pages}\n\n"
        if not reels:
            return header + "Reels tidak ditemukan di halaman ini."
        body = "\n\n".join(self.reel_card_line(reel) for reel in reels)
        selected = sorted(set(selected_slots or []))
        if selected:
            body += "\n\nChoiced number " + ", ".join(str(slot) for slot in selected)
        return header + body

    def caption(self, title: str, description: str) -> str:
        title = (title or "").strip()
        description = (description or "").strip()
        if not title and not description:
            return ""
        combined = title if not description else f"{title}\n\n{description}" if title else description
        if len(combined) <= 1024:
            return combined
        chunks = chunk_text(combined, limit=1024)
        return chunks[0] if chunks else combined[:1024]

    def download_caption(self, result: CdnResult) -> str:
        return self.caption(result.title, result.description)

    def error_text(self, message: str) -> str:
        return f"❌ Gagal memproses video.\nAlasan: {message}"
