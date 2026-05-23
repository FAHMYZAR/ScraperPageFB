from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def split_dash_tracks(renditions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    video_tracks: List[Dict[str, Any]] = []
    audio_tracks: List[Dict[str, Any]] = []

    for item in renditions or []:
        if not isinstance(item, dict):
            continue
        base_url = str(item.get("base_url", "")).strip()
        if not base_url:
            continue

        track = dict(item)
        track["bandwidth"] = _as_int(track.get("bandwidth"), 0)
        track["width"] = _as_int(track.get("width"), 0)
        track["height"] = _as_int(track.get("height"), 0)
        mime = str(track.get("mime_type", "")).lower()

        is_video = mime.startswith("video/") or track["height"] > 0 or track["width"] > 0
        is_audio = mime.startswith("audio/") or (not is_video and track["height"] == 0 and track["width"] == 0)

        if is_video:
            video_tracks.append(track)
        elif is_audio:
            audio_tracks.append(track)

    video_tracks.sort(key=lambda t: (t["height"], t["width"], t["bandwidth"]), reverse=True)
    audio_tracks.sort(key=lambda t: t["bandwidth"], reverse=True)
    return video_tracks, audio_tracks


def choose_best_video_track(video_tracks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return video_tracks[0] if video_tracks else None


def choose_best_audio_track(audio_tracks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return audio_tracks[0] if audio_tracks else None


def build_video_track_options(video_tracks: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    options: List[Dict[str, Any]] = []
    seen_urls = set()
    for track in video_tracks:
        url = str(track.get("base_url", "")).strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        quality = (
            str(track.get("quality_label", "")).strip()
            or str(track.get("quality_class", "")).strip()
            or (
                f"{_as_int(track.get('width'))}x{_as_int(track.get('height'))}"
                if _as_int(track.get("height")) > 0
                else "video"
            )
        )
        bandwidth_kbps = max(1, _as_int(track.get("bandwidth"), 0) // 1000) if _as_int(track.get("bandwidth"), 0) > 0 else 0
        label = quality if bandwidth_kbps == 0 else f"{quality} ({bandwidth_kbps} kbps)"
        options.append({"label": label, "track": track})
        if len(options) >= limit:
            break
    return options


def summarize_renditions(renditions: List[Dict[str, Any]], limit: int = 12) -> List[str]:
    lines: List[str] = []
    for idx, item in enumerate(renditions[:limit], 1):
        width = _as_int(item.get("width"), 0)
        height = _as_int(item.get("height"), 0)
        size_label = f"{width}x{height}" if width > 0 and height > 0 else "audio"
        quality = str(item.get("quality_label", "")).strip() or str(item.get("quality_class", "")).strip() or size_label
        mime = str(item.get("mime_type", "")).strip() or "-"
        bandwidth = _as_int(item.get("bandwidth"), 0)
        bw_text = f"{bandwidth:,}" if bandwidth else "-"
        base_url = str(item.get("base_url", "")).strip()
        lines.append(f"{idx}. {quality} | {mime} | bw {bw_text}\n   {base_url}")

    if len(renditions) > limit:
        lines.append(f"... dan {len(renditions) - limit} rendition lainnya.")
    return lines


def download_file(
    url: str,
    output_path: Path,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 60,
    session: Optional[requests.Session] = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    requester = session or requests
    request_kwargs = {
        "headers": headers or {},
        "stream": True,
        "timeout": timeout,
    }
    with requester.get(url, **request_kwargs) as response:
        response.raise_for_status()
        with output_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if chunk:
                    handle.write(chunk)
    return output_path


def merge_video_audio_ffmpeg(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    ffmpeg_bin: str = "ffmpeg",
    timeout: int = 1800,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        ffmpeg_bin,
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
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        stderr = proc.stderr.strip()[-1000:]
        raise RuntimeError(f"ffmpeg failed: {stderr or proc.returncode}")
    return output_path


def ensure_ffmpeg_available(ffmpeg_bin: str = "ffmpeg") -> None:
    command = [ffmpeg_bin, "-version"]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=20)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg is not available in PATH.")


def safe_filename_part(text: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in text)
    return safe.strip("_") or "reel"


def prepare_media_file(
    reel_id: str,
    video_url: str,
    audio_url: Optional[str],
    work_dir: Path,
    headers: Optional[Dict[str, str]] = None,
    session: Optional[requests.Session] = None,
) -> Path:
    reel_part = safe_filename_part(reel_id)
    video_file = work_dir / f"{reel_part}_video.mp4"
    download_file(video_url, video_file, headers=headers, session=session)

    if not audio_url:
        return video_file

    ensure_ffmpeg_available()
    audio_file = work_dir / f"{reel_part}_audio.m4a"
    output_file = work_dir / f"{reel_part}_merged.mp4"
    download_file(audio_url, audio_file, headers=headers, session=session)
    return merge_video_audio_ffmpeg(video_file, audio_file, output_file)
