from __future__ import annotations

import asyncio
import math
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

    async def get_duration_seconds(self, media_path: Path, ffprobe_bin: Optional[str] = None) -> float:
        binary = shutil.which(ffprobe_bin or "ffprobe")
        if not binary:
            raise RuntimeError("FFprobe tidak terinstall atau tidak ada di PATH.")
        process = await asyncio.create_subprocess_exec(
            binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="ignore")[-500:]
            raise RuntimeError(f"FFprobe gagal membaca durasi: {message}")
        try:
            return max(0.1, float(stdout.decode("utf-8", errors="ignore").strip()))
        except ValueError as exc:
            raise RuntimeError("Durasi video tidak bisa dibaca.") from exc

    async def split_video_by_size(self, input_path: Path, output_dir: Path, max_part_bytes: int) -> list[Path]:
        binary = self.validate_ffmpeg()
        file_size = input_path.stat().st_size
        if file_size <= max_part_bytes:
            return [input_path]

        output_dir.mkdir(parents=True, exist_ok=True)
        duration = await self.get_duration_seconds(input_path)
        part_count = max(2, math.ceil(file_size / max_part_bytes))
        last_parts: list[Path] = []

        for _ in range(4):
            for old_part in output_dir.glob(f"{input_path.stem}_part_*.mp4"):
                old_part.unlink(missing_ok=True)
            segment_time = max(1, math.ceil(duration / part_count))
            pattern = output_dir / f"{input_path.stem}_part_%03d.mp4"
            process = await asyncio.create_subprocess_exec(
                binary,
                "-y",
                "-i",
                str(input_path),
                "-map",
                "0",
                "-c",
                "copy",
                "-f",
                "segment",
                "-segment_time",
                str(segment_time),
                "-reset_timestamps",
                "1",
                str(pattern),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
            except asyncio.TimeoutError as exc:
                process.kill()
                await process.communicate()
                raise RuntimeError("Split FFmpeg timeout.") from exc
            if process.returncode != 0:
                message = stderr.decode("utf-8", errors="ignore")[-500:]
                raise RuntimeError(f"Split FFmpeg gagal: {message}")

            parts = sorted(output_dir.glob(f"{input_path.stem}_part_*.mp4"))
            if not parts:
                raise RuntimeError("Split FFmpeg tidak menghasilkan part.")
            last_parts = parts
            if all(part.stat().st_size <= max_part_bytes for part in parts):
                return parts
            part_count *= 2

        oversized = [part.name for part in last_parts if part.stat().st_size > max_part_bytes]
        raise RuntimeError(f"Split selesai, tapi part masih terlalu besar: {', '.join(oversized)}")

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
