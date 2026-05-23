from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

import requests

from CLI_Mode.facebook_reels_cli import DEFAULT_HEADERS

CHUNK_SIZE = 1024 * 1024


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return cleaned.strip("_") or "reel"


def _resolve_session(session: Optional[requests.Session]) -> requests.Session:
    return session or requests.Session()


def download_file(
    url: str,
    output_path: Path,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 60,
    session: Optional[requests.Session] = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request_session = _resolve_session(session)
    response = request_session.get(
        url,
        headers=headers or DEFAULT_HEADERS,
        stream=True,
        timeout=timeout,
        allow_redirects=True,
    )
    response.raise_for_status()

    with output_path.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                handle.write(chunk)

    return output_path


def _ffmpeg_binary(ffmpeg_bin: str) -> Optional[str]:
    resolved = shutil.which(ffmpeg_bin)
    if resolved:
        return resolved
    candidate = Path(ffmpeg_bin)
    if candidate.exists():
        return str(candidate)
    return None


def merge_video_audio_ffmpeg(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    binary = _ffmpeg_binary(ffmpeg_bin)
    if not binary:
        raise RuntimeError("ffmpeg not found")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
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
    ]
    subprocess.run(command, check=True, capture_output=True)
    return output_path


def prepare_media_file(
    reel_id: str,
    video_url: str,
    audio_url: Optional[str],
    work_dir: Path,
    headers: Optional[Dict[str, str]] = None,
    session: Optional[requests.Session] = None,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    safe_reel = _safe_stem(reel_id)
    video_path = work_dir / f"{safe_reel}_video.mp4"
    download_file(video_url, video_path, headers=headers, timeout=60, session=session)

    if not audio_url:
        return video_path

    audio_path = work_dir / f"{safe_reel}_audio.m4a"
    output_path = work_dir / f"{safe_reel}.mp4"
    try:
        download_file(audio_url, audio_path, headers=headers, timeout=60, session=session)
        return merge_video_audio_ffmpeg(video_path, audio_path, output_path, ffmpeg_bin=ffmpeg_bin)
    except Exception:
        return video_path
