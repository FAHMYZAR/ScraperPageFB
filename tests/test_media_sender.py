from pathlib import Path

import asyncio

from services.media_sender import MediaSender


class FakeBot:
    def __init__(self) -> None:
        self.sent_document = False
        self.sent_video = False
        self.media_group_count = 0
        self.sent_message = False

    async def send_document(self, **kwargs):
        self.sent_document = True

    async def send_video(self, **kwargs):
        self.sent_video = True

    async def send_media_group(self, **kwargs):
        self.media_group_count += len(kwargs["media"])

    async def send_message(self, **kwargs):
        self.sent_message = True


def test_large_file_is_sent_as_document(tmp_path):
    file_path = tmp_path / "large.mp4"
    file_path.write_bytes(b"123456")
    bot = FakeBot()

    success, mode = asyncio.run(MediaSender(max_upload_bytes=3).send_video_file(bot, 1, file_path, "caption"))

    assert success is True
    assert mode == "document_large_file"
    assert bot.sent_document is True
    assert bot.sent_video is False


def test_video_parts_are_sent_as_media_group(tmp_path):
    part1 = tmp_path / "part1.mp4"
    part2 = tmp_path / "part2.mp4"
    part1.write_bytes(b"1")
    part2.write_bytes(b"2")
    bot = FakeBot()

    success, mode = asyncio.run(MediaSender().send_video_parts(bot, 1, [part1, part2], "caption"))

    assert success is True
    assert mode == "video_parts"
    assert bot.media_group_count == 2
