from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import asyncio
import aiohttp
import shutil

from CLI_Mode.facebook_reels_cli import DEFAULT_HEADERS
from models import CdnResult, CdnVariant
from services.ffmpeg_merger import FFmpegMerger

from services.session_manager import SessionManager


class VideoDownloader:
    CHUNK_SIZE = 1024 * 1024

    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        ffmpeg_bin: str = "ffmpeg",
        timeout_seconds: int = 120,
        max_retries: int = 3,
    ) -> None:
        self.session_manager = session_manager
        self.ffmpeg_bin = ffmpeg_bin
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(1, max_retries)
        self.merger = FFmpegMerger(ffmpeg_bin=ffmpeg_bin)

    @staticmethod
    def choose_best_video(variants: Sequence[CdnVariant]) -> Optional[CdnVariant]:
        videos = [item for item in variants if item.url and not item.is_audio_only]
        if not videos:
            return None
        return sorted(
            videos,
            key=lambda item: (
                item.height or 0,
                item.width or 0,
                item.bitrate or 0,
            ),
            reverse=True,
        )[0]

    @staticmethod
    def choose_best_audio(variants: Sequence[CdnVariant]) -> Optional[CdnVariant]:
        audios = [item for item in variants if item.url and (item.is_audio_only or item.mime_type.startswith("audio/"))]
        if not audios:
            return None
        return sorted(audios, key=lambda item: item.bitrate or 0, reverse=True)[0]

    @staticmethod
    def cleanup_temp_files(paths: Iterable[Path]) -> None:
        path_list = list(paths)
        for path in path_list:
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                elif path.exists():
                    path.unlink()
            except OSError:
                pass
        for path in path_list:
            parent = path.parent
            try:
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
            except OSError:
                pass

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = dict(DEFAULT_HEADERS)
        if extra:
            headers.update(extra)
        if self.session_manager and self.session_manager.store.cookie_records:
            cookie = "; ".join(
                f"{record.get('name')}={record.get('value')}"
                for record in self.session_manager.store.cookie_records
                if record.get("name") and record.get("value")
            )
            if cookie:
                headers["Cookie"] = cookie
        return headers

    async def download_stream(self, url: str, output_path: Path, headers: Optional[Dict[str, str]] = None) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        last_error: Optional[BaseException] = None
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession(timeout=timeout, headers=self._headers(headers)) as session:
                    async with session.get(url, allow_redirects=True) as response:
                        response.raise_for_status()
                        with output_path.open("wb") as handle:
                            async for chunk in response.content.iter_chunked(self.CHUNK_SIZE):
                                if chunk:
                                    handle.write(chunk)
                if output_path.exists() and output_path.stat().st_size > 0:
                    return output_path
                raise RuntimeError("File hasil download kosong.")
            except Exception as exc:
                last_error = exc
                if output_path.exists():
                    output_path.unlink(missing_ok=True)
                if attempt + 1 < self.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 5))
        raise RuntimeError(f"Download gagal: {last_error}") from last_error

    async def download_video_stream(self, url: str, output_path: Path, headers: Optional[Dict[str, str]] = None) -> Path:
        return await self.download_stream(url, output_path, headers=headers)

    async def download_audio_stream(self, url: str, output_path: Path, headers: Optional[Dict[str, str]] = None) -> Path:
        return await self.download_stream(url, output_path, headers=headers)

    async def detect_has_audio(self, file_path: Path) -> bool:
        return await self.merger.has_audio_stream(file_path)

    async def split_video_by_size(self, file_path: Path, output_dir: Path, max_part_bytes: int) -> list[Path]:
        return await self.merger.split_video_by_size(file_path, output_dir, max_part_bytes)

    async def prepare_final_mp4(
        self,
        reel_id: str,
        video_url: str,
        audio_url: Optional[str],
        work_dir: Path,
        headers: Optional[Dict[str, str]] = None,
    ) -> Path:
        safe_id = self.safe_stem(reel_id)
        video_path = work_dir / f"{safe_id}_video.mp4"
        audio_path = work_dir / f"{safe_id}_audio.m4a"
        output_path = work_dir / f"{safe_id}.mp4"
        await self.download_video_stream(video_url, video_path, headers=headers)
        if not audio_url:
            return video_path
        await self.download_audio_stream(audio_url, audio_path, headers=headers)
        return await self.merger.merge_video_audio(video_path, audio_path, output_path)

    async def prepare_cdn_result(self, result: CdnResult, work_dir: Path, file_stem: Optional[str] = None) -> Path:
        best_video = result.best_video or self.choose_best_video(result.video_variants)
        best_audio = result.best_audio or self.choose_best_audio(result.audio_variants)
        video_url = result.video_url or (best_video.url if best_video else None)
        audio_url = result.audio_url or (best_audio.url if best_audio else None)
        if not video_url:
            raise RuntimeError("CDN video tidak ditemukan.")
        stem = file_stem or result.title or result.reel_id or "facebook_video"
        final = await self.prepare_final_mp4(stem, video_url, audio_url, work_dir)
        if not audio_url and not await self.detect_has_audio(final):
            raise RuntimeError("Video silent dan audio CDN tidak tersedia.")
        result.final_file_path = str(final)
        return final

    async def resolve_and_prepare(
        self,
        reel_id: str,
        video_url: str,
        audio_url: Optional[str],
        headers: Optional[Dict[str, str]] = None,
    ) -> Path:
        work_dir = Path(tempfile.mkdtemp(prefix="reel_media_"))
        return await self.prepare_final_mp4(reel_id, video_url, audio_url, work_dir, headers=headers)

    @staticmethod
    def safe_stem(value: str) -> str:
        import re

        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
        return cleaned.strip("_")[:120] or f"facebook_video_{int(time.time())}"
