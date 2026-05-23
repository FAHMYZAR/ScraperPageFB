from __future__ import annotations

from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.base import BotServices, get_user_state
from models import CdnResult


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
            state.last_detail = result
            await loading.delete()
            await update.message.reply_text(
                self._quality_text(result),
                reply_markup=self.services.keyboards.build_download_quality_keyboard(result),
            )
            return True
        except Exception as exc:
            await update.message.reply_text(
                self.services.formatter.error_text(str(exc)),
                reply_markup=self.services.keyboards.build_error_keyboard(),
            )
            return True

    async def handle_quality_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, choice: str) -> None:
        state = get_user_state(context)
        result = state.last_detail
        if not isinstance(result, CdnResult):
            if update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text(
                    "Data CDN belum ada. Kirim link video dulu.",
                    reply_markup=self.services.keyboards.build_download_keyboard(),
                )
            return
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(f"Choiced quality {self._choice_label(result, choice)}\n\n🎮 Loading...\n▰▰▰▰▱ Download dan merge...")
        await self._download_and_send(update, context, result, choice)

    async def _download_and_send(self, update: Update, context: ContextTypes.DEFAULT_TYPE, result: CdnResult, choice: str) -> None:
        work_dir = self.services.temp_dir_for_update(update) / (result.reel_id or "download")
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            selected = self._selected_variant(result, choice)
            if selected is not None:
                result.best_video = selected
                result.video_url = selected.url
                result.quality = selected.quality
                result.merged_audio_video_url = selected.url if selected.has_audio else None
            caption = self.services.formatter.download_caption(result)
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
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=self.services.formatter.error_text(f"{reason}; split juga gagal: {part_reason}"),
                        reply_markup=self.services.keyboards.build_error_keyboard(),
                    )
        except Exception as exc:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=self.services.formatter.error_text(str(exc)),
                reply_markup=self.services.keyboards.build_error_keyboard(),
            )
        finally:
            self.services.downloader_for_update(update).cleanup_temp_files(work_dir.glob("*"))

    def _selected_variant(self, result: CdnResult, choice: str):
        variants = [variant for variant in result.video_variants if variant.url and not variant.is_audio_only]
        if choice == "best":
            return self.services.downloader.choose_best_video(variants) if variants else result.best_video
        try:
            index = int(choice)
        except ValueError:
            return result.best_video
        if 0 <= index < len(variants):
            return variants[index]
        return result.best_video

    def _choice_label(self, result: CdnResult, choice: str) -> str:
        variant = self._selected_variant(result, choice)
        if variant is None:
            return "Best"
        return variant.quality or (f"{variant.height}p" if variant.height else "Video")

    def _quality_text(self, result: CdnResult) -> str:
        lines = ["Pilih resolusi video yang mau didownload:"]
        if result.title:
            lines.extend(["", result.title])
        variants = [variant for variant in result.video_variants if variant.url and not variant.is_audio_only]
        for index, variant in enumerate(variants[:12], 1):
            label = variant.quality or (f"{variant.height}p" if variant.height else "Video")
            size = f"{variant.width}x{variant.height}" if variant.width and variant.height else "-"
            bitrate = f"{variant.bitrate} bps" if variant.bitrate else "-"
            lines.append(f"{index}. {label} | {size} | {bitrate}")
        return "\n".join(lines)
