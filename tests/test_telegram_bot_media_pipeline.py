import unittest

from telegram_media_pipeline import (
    build_video_track_options,
    choose_best_audio_track,
    choose_best_video_track,
    split_dash_tracks,
)


class TelegramMediaPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.renditions = [
            {
                "id": "v1080",
                "mime_type": "video/mp4",
                "width": 1080,
                "height": 1920,
                "bandwidth": 3900000,
                "quality_label": "1080p",
                "base_url": "https://cdn/video_1080.mp4",
            },
            {
                "id": "v720",
                "mime_type": "video/mp4",
                "width": 720,
                "height": 1280,
                "bandwidth": 2200000,
                "quality_label": "720p",
                "base_url": "https://cdn/video_720.mp4",
            },
            {
                "id": "a128",
                "mime_type": "audio/mp4",
                "width": 0,
                "height": 0,
                "bandwidth": 128000,
                "quality_label": "",
                "base_url": "https://cdn/audio_128.m4a",
            },
            {
                "id": "a64",
                "mime_type": "audio/mp4",
                "width": 0,
                "height": 0,
                "bandwidth": 64000,
                "quality_label": "",
                "base_url": "https://cdn/audio_64.m4a",
            },
        ]

    def test_split_dash_tracks(self) -> None:
        video_tracks, audio_tracks = split_dash_tracks(self.renditions)
        self.assertEqual(len(video_tracks), 2)
        self.assertEqual(len(audio_tracks), 2)

    def test_choose_best_tracks(self) -> None:
        video_tracks, audio_tracks = split_dash_tracks(self.renditions)
        best_video = choose_best_video_track(video_tracks)
        best_audio = choose_best_audio_track(audio_tracks)
        self.assertEqual(best_video["id"], "v1080")
        self.assertEqual(best_audio["id"], "a128")

    def test_build_video_track_options(self) -> None:
        video_tracks, _ = split_dash_tracks(self.renditions)
        options = build_video_track_options(video_tracks)
        self.assertEqual(len(options), 2)
        self.assertIn("1080p", options[0]["label"])
        self.assertEqual(options[0]["track"]["id"], "v1080")


if __name__ == "__main__":
    unittest.main()
