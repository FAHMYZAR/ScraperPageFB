from __future__ import annotations

from pathlib import Path
from typing import Optional

from telegram import InlineKeyboardMarkup
from telegram.error import TelegramError

from models import CdnResult
from utils.performance import chunk_text


class MediaSender:
    def __init__(self, text_limit: int = 3900) -> None:
        self.text_limit = max(100, text_limit)

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
