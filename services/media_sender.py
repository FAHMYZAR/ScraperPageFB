from __future__ import annotations

from pathlib import Path
from typing import Optional

from telegram import InlineKeyboardMarkup, InputMediaVideo
from telegram.error import TelegramError

from models import CdnResult
from utils.performance import chunk_text


class MediaSender:
    def __init__(self, text_limit: int = 3900, max_upload_bytes: int = 50 * 1024 * 1024) -> None:
        self.text_limit = max(100, text_limit)
        self.max_upload_bytes = max_upload_bytes

    async def send_text(
        self,
        bot,
        chat_id: int,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        parse_mode: Optional[str] = None,
    ) -> list[int]:
        chunks = chunk_text(text, self.text_limit)
        if not chunks:
            chunks = [""]

        message_ids: list[int] = []
        for index, chunk in enumerate(chunks):
            sent = await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=parse_mode,
                disable_web_page_preview=True,
                reply_markup=reply_markup if index == 0 else None,
            )
            message_ids.append(sent.message_id)
        return message_ids

    async def send_loading(self, bot, chat_id: int, text: str) -> int:
        sent = await bot.send_message(chat_id=chat_id, text=text)
        return sent.message_id

    async def send_video_file(
        self,
        bot,
        chat_id: int,
        file_path: Path,
        caption: str,
        width: int = 0,
        height: int = 0,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> tuple[bool, str]:
        if file_path.stat().st_size > self.max_upload_bytes:
            try:
                with file_path.open("rb") as handle:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=handle,
                        caption=caption,
                        reply_markup=reply_markup,
                    )
                return True, "document_large_file"
            except TelegramError as exc_doc:
                return False, f"Video berhasil diproses, tapi ukuran file melebihi batas upload Telegram. Dokumen juga gagal: {exc_doc}"
        try:
            with file_path.open("rb") as handle:
                await bot.send_video(
                    chat_id=chat_id,
                    video=handle,
                    caption=caption,
                    width=width or None,
                    height=height or None,
                    supports_streaming=True,
                    reply_markup=reply_markup,
                )
            return True, "video"
        except TelegramError as exc_video:
            try:
                with file_path.open("rb") as handle:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=handle,
                        caption=caption,
                        reply_markup=reply_markup,
                    )
                return True, f"document_fallback:{exc_video}"
            except TelegramError as exc_doc:
                return False, f"video={exc_video}; document={exc_doc}"

    async def send_video_url(
        self,
        bot,
        chat_id: int,
        video_url: str,
        caption: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> tuple[bool, str]:
        try:
            await bot.send_video(
                chat_id=chat_id,
                video=video_url,
                caption=caption,
                supports_streaming=True,
                reply_markup=reply_markup,
            )
            return True, "remote_url"
        except TelegramError as exc:
            return False, str(exc)

    async def send_video_parts(
        self,
        bot,
        chat_id: int,
        file_paths: list[Path],
        caption: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> tuple[bool, str]:
        if not file_paths:
            return False, "Tidak ada part video untuk dikirim."

        total = len(file_paths)
        try:
            for start in range(0, total, 10):
                chunk = file_paths[start:start + 10]
                handles = [path.open("rb") for path in chunk]
                try:
                    media = []
                    for offset, handle in enumerate(handles):
                        part_number = start + offset + 1
                        part_caption = f"Part {part_number}/{total}"
                        if part_number == 1 and caption:
                            part_caption = f"{caption}\n\n{part_caption}"
                        media.append(InputMediaVideo(media=handle, caption=part_caption, supports_streaming=True))
                    await bot.send_media_group(chat_id=chat_id, media=media)
                finally:
                    for handle in handles:
                        handle.close()
            if reply_markup:
                await bot.send_message(chat_id=chat_id, text="Semua part terkirim.", reply_markup=reply_markup)
            return True, "video_parts"
        except TelegramError as exc:
            return False, str(exc)
