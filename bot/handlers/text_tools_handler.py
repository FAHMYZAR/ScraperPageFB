from __future__ import annotations

from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.base import BotServices, get_user_state
from utils.json_payload import to_json_text


class TextToolsHandler:
    def __init__(self, services: BotServices) -> None:
        self.services = services

    async def prompt_scrape_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        state = get_user_state(context)
        state.awaiting = "text_scrape_page_url"
        text = "Kirim URL Facebook Page/Reels. Output akan dikirim sebagai JSON teks saja."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=self.services.keyboards.build_text_tools_keyboard())
            return
        if update.message:
            await update.message.reply_text(text, reply_markup=self.services.keyboards.build_text_tools_keyboard())

    async def prompt_download_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        state = get_user_state(context)
        state.awaiting = "text_download_link_url"
        text = "Kirim link video/reels Facebook. Output CDN/download link akan dikirim sebagai JSON teks saja."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=self.services.keyboards.build_text_tools_keyboard())
            return
        if update.message:
            await update.message.reply_text(text, reply_markup=self.services.keyboards.build_text_tools_keyboard())

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        state = get_user_state(context)
        if not update.message or not update.message.text:
            return False
        if state.awaiting == "text_scrape_page_url":
            await self._handle_scrape_page(update, context, update.message.text.strip())
            return True
        if state.awaiting == "text_download_link_url":
            await self._handle_download_link(update, context, update.message.text.strip())
            return True
        return False

    async def _handle_scrape_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE, raw_url: str) -> None:
        state = get_user_state(context)
        state.awaiting = None
        try:
            page_url = self.services.resolver.normalize_page_url(raw_url)
            loading = await update.message.reply_text("Mengambil data page sebagai JSON...")
            scraper = self.services.scraper_for_update(update)
            session = await scraper.validate_session(page_url)
            page_info = await scraper.fetch_page_info(page_url)
            reels = await scraper.fetch_reels(page_url, order="newest", max_reels=None, use_browser_scroll=True)
            payload = {
                "type": "scrape_page",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "input_url": raw_url,
                "normalized_url": page_url,
                "session": session.to_dict(),
                "page_info": page_info.to_dict(),
                "total_reels": len(reels),
                "reels": [reel.to_dict() for reel in reels],
            }
            await loading.delete()
            await self.services.media_sender.send_text(
                context.bot,
                update.effective_chat.id,
                to_json_text(payload),
                reply_markup=self.services.keyboards.build_text_tools_keyboard(),
            )
        except Exception as exc:
            await update.message.reply_text(
                self.services.formatter.error_text(str(exc)),
                reply_markup=self.services.keyboards.build_text_tools_keyboard(),
            )

    async def _handle_download_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE, raw_url: str) -> None:
        state = get_user_state(context)
        state.awaiting = None
        try:
            if not self.services.resolver.is_facebook_video_url(raw_url):
                raise ValueError("URL tidak valid atau bukan link video Facebook.")
            loading = await update.message.reply_text("Resolve link dan CDN sebagai JSON...")
            resolved_url = await self.services.resolver.resolve_share_url(raw_url)
            result = await self.services.scraper_for_update(update).resolve_cdn(resolved_url)
            payload = {
                "type": "download_link",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "input_url": raw_url,
                "resolved_url": resolved_url,
                "cdn": result.to_dict(),
            }
            await loading.delete()
            await self.services.media_sender.send_text(
                context.bot,
                update.effective_chat.id,
                to_json_text(payload),
                reply_markup=self.services.keyboards.build_text_tools_keyboard(),
            )
        except Exception as exc:
            await update.message.reply_text(
                self.services.formatter.error_text(str(exc)),
                reply_markup=self.services.keyboards.build_text_tools_keyboard(),
            )
