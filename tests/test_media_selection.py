from models import CdnVariant
from services.video_downloader import VideoDownloader


def test_choose_best_video_prefers_highest_resolution_then_bitrate():
    variants = [
        CdnVariant(url="low", quality="360p", width=640, height=360, bitrate=500, mime_type="video/mp4"),
        CdnVariant(url="mid", quality="720p", width=1280, height=720, bitrate=1800, mime_type="video/mp4"),
        CdnVariant(url="high", quality="1080p", width=1920, height=1080, bitrate=1200, mime_type="video/mp4"),
    ]

    assert VideoDownloader.choose_best_video(variants).url == "high"


def test_choose_best_audio_prefers_audio_only_highest_bitrate():
    variants = [
        CdnVariant(url="video", quality="720p", width=1280, height=720, bitrate=1500, mime_type="video/mp4"),
        CdnVariant(url="audio-low", quality=None, width=None, height=None, bitrate=64, mime_type="audio/mp4", is_audio_only=True),
        CdnVariant(url="audio-high", quality=None, width=None, height=None, bitrate=128, mime_type="audio/mp4", is_audio_only=True),
    ]

    assert VideoDownloader.choose_best_audio(variants).url == "audio-high"
