from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Dict, Optional

from CLI_Mode.facebook_reels_cli import DEFAULT_HEADERS

from services.media_pipeline import download_file, prepare_media_file

from services.session_manager import SessionManager


class VideoDownloader:
    def __init__(self, session_manager: SessionManager, ffmpeg_bin: str = "ffmpeg") -> None:
        self.session_manager = session_manager
        self.ffmpeg_bin = ffmpeg_bin

    async def download_video_stream(self, url: str, output_path: Path, headers: Optional[Dict[str, str]] = None) -> Path:
        session = self.session_manager.build_requests_session()
        return await asyncio.to_thread(download_file, url, output_path, headers or DEFAULT_HEADERS, 60, session)

    async def prepare_final_mp4(
        self,
        reel_id: str,
        video_url: str,
        audio_url: Optional[str],
        work_dir: Path,
        headers: Optional[Dict[str, str]] = None,
    ) -> Path:
        session = self.session_manager.build_requests_session()
        return await asyncio.to_thread(
            prepare_media_file,
            reel_id,
            video_url,
            audio_url,
            work_dir,
            headers or DEFAULT_HEADERS,
            session,
        )

    async def resolve_and_prepare(
        self,
        reel_id: str,
        video_url: str,
        audio_url: Optional[str],
        headers: Optional[Dict[str, str]] = None,
    ) -> Path:
        work_dir = Path(tempfile.mkdtemp(prefix="reel_media_"))
        return await self.prepare_final_mp4(reel_id, video_url, audio_url, work_dir, headers=headers)
