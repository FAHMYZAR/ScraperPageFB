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
        text = "Kirim link video/reels Facebook yang ingin didownload."
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
        work_dir = None
        try:
            if not self.services.resolver.is_facebook_video_url(raw_url):
                await update.message.reply_text(
                    self.services.formatter.error_text("URL tidak valid atau bukan link video Facebook."),
                    reply_markup=self.services.keyboards.build_error_keyboard(),
                )
                return True

            loading = await update.message.reply_text("🎮 Loading...\n▰▰▱▱▱ Resolve link...")
            resolved = await self.services.resolver.resolve_share_url(raw_url)
            await loading.edit_text("🎮 Loading...\n▰▰▰▱▱ Ambil CDN...")
            result = await self.services.scraper_for_update(update).resolve_cdn(resolved)
            if not result.best_url:
                await update.message.reply_text(
                    self.services.formatter.error_text("CDN video tidak ditemukan."),
                    reply_markup=self.services.keyboards.build_error_keyboard(),
                )
                return True
            caption = self.services.formatter.download_caption(result)
            work_dir = self.services.temp_dir_for_update(update) / (result.reel_id or "download")
            work_dir.mkdir(parents=True, exist_ok=True)
            await loading.edit_text("🎮 Loading...\n▰▰▰▰▱ Download dan merge...")
            media_path = await self.services.downloader_for_update(update).prepare_cdn_result(result, work_dir)
            success, reason = await self.services.media_sender.send_video_file(
                context.bot,
                update.effective_chat.id,
                media_path,
                caption,
                reply_markup=self.services.keyboards.build_download_keyboard(),
            )
            if not success:
                part_dir = work_dir / "parts"
                parts = await self.services.downloader_for_update(update).split_video_by_size(
                    media_path,
                    part_dir,
                    self.services.media_sender.max_upload_bytes,
                )
                success, part_reason = await self.services.media_sender.send_video_parts(
                    context.bot,
                    update.effective_chat.id,
                    parts,
                    caption,
                    reply_markup=self.services.keyboards.build_download_keyboard(),
                )
                if not success:
                    await update.message.reply_text(
                        self.services.formatter.error_text(f"{reason}; split juga gagal: {part_reason}"),
                        reply_markup=self.services.keyboards.build_error_keyboard(),
                    )
            return True
        except Exception as exc:
            await update.message.reply_text(
                self.services.formatter.error_text(str(exc)),
                reply_markup=self.services.keyboards.build_error_keyboard(),
            )
            return True
        finally:
            if work_dir is not None:
                self.services.downloader_for_update(update).cleanup_temp_files(work_dir.glob("*"))
