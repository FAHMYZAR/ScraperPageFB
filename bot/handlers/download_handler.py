from __future__ import annotations

from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.base import BotServices, get_user_state


class DownloadHandler:
    def __init__(self, services: BotServices) -> None:
        self.services = services

    async def prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        state = get_user_state(context)
        state.awaiting = "download_url"
        text = "Kirim URL reel / video Facebook / CDN langsung yang ingin diunduh."
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            await query.edit_message_text(text, reply_markup=self.services.keyboards.build_download_keyboard())
            return
        if update.message:
            await update.message.reply_text(text, reply_markup=self.services.keyboards.build_download_keyboard())

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        state = get_user_state(context)
        if state.awaiting != "download_url" or not update.message or not update.message.text:
            return False

        raw_url = update.message.text.strip()
        state.awaiting = None
        try:
            result = await self.services.scraper.resolve_cdn(raw_url)
            if not result.best_url:
                await update.message.reply_text(self.services.formatter.error_text("Gagal menemukan URL video."))
                return True

            caption = self.services.formatter.download_caption(result)
            work_dir = Path(self.services.session_manager.session_file).parent / "downloads"
            work_dir.mkdir(parents=True, exist_ok=True)

            if result.video_url and (result.audio_url or result.merged_audio_video_url):
                try:
                    media_path = await self.services.downloader.prepare_final_mp4(
                        result.reel_id or "download",
                        result.video_url,
                        result.audio_url,
                        work_dir,
                    )
                    success, _ = await self.services.media_sender.send_video_file(
                        context.bot,
                        update.effective_chat.id,
                        media_path,
                        caption,
                    )
                    if success:
                        return True
                except Exception:
                    pass

            success, _ = await self.services.media_sender.send_video_url(
                context.bot,
                update.effective_chat.id,
                result.best_url,
                caption,
            )
            if not success:
                await update.message.reply_text(result.best_url)
            return True
        except Exception as exc:
            await update.message.reply_text(self.services.formatter.error_text(f"Download gagal: {exc}"))
            return True
