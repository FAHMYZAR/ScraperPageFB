from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Optional


class FFmpegMerger:
    def __init__(self, ffmpeg_bin: str = "ffmpeg", timeout_seconds: int = 180) -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.timeout_seconds = timeout_seconds

    def validate_ffmpeg(self) -> str:
        resolved = shutil.which(self.ffmpeg_bin)
        if resolved:
            return resolved
        candidate = Path(self.ffmpeg_bin)
        if candidate.exists():
            return str(candidate)
        raise RuntimeError("FFmpeg tidak terinstall atau tidak ada di PATH.")

    async def merge_video_audio(self, video_path: Path, audio_path: Path, output_path: Path) -> Path:
        binary = self.validate_ffmpeg()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            binary,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise RuntimeError("Merge FFmpeg timeout.") from exc
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="ignore")[-500:]
            raise RuntimeError(f"Merge FFmpeg gagal: {message}")
        self.validate_output(output_path)
        return output_path

    def validate_output(self, output_path: Path) -> None:
        if not output_path.exists() or output_path.stat().st_size <= 0:
            raise RuntimeError("Output MP4 tidak valid.")

    async def has_audio_stream(self, media_path: Path, ffprobe_bin: Optional[str] = None) -> bool:
        binary = shutil.which(ffprobe_bin or "ffprobe")
        if not binary:
            return False
        process = await asyncio.create_subprocess_exec(
            binary,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(media_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=30)
        return b"audio" in stdout
