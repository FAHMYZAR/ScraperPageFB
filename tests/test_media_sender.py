from pathlib import Path

import asyncio

from services.media_sender import MediaSender


class FakeBot:
    def __init__(self) -> None:
        self.sent_document = False
        self.sent_video = False

    async def send_document(self, **kwargs):
        self.sent_document = True

    async def send_video(self, **kwargs):
        self.sent_video = True


def test_large_file_is_sent_as_document(tmp_path):
    file_path = tmp_path / "large.mp4"
    file_path.write_bytes(b"123456")
    bot = FakeBot()

    success, mode = asyncio.run(MediaSender(max_upload_bytes=3).send_video_file(bot, 1, file_path, "caption"))

    assert success is True
    assert mode == "document_large_file"
    assert bot.sent_document is True
    assert bot.sent_video is False
