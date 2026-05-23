from __future__ import annotations

from dataclasses import replace
from typing import List

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from bot.handlers.base import BotServices, get_user_state
from models import Reel
from utils.performance import paginate


class ScrapeHandler:
    def __init__(self, services: BotServices) -> None:
        self.services = services

    async def prompt_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        state = get_user_state(context)
        state.awaiting = "scan_target"
        state.reset_scan()
        text = "Kirim URL Facebook Page/Reels yang ingin di-scrape."
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            await query.edit_message_text(text, reply_markup=self.services.keyboards.build_main_menu_keyboard())
            return
        if update.message:
            await update.message.reply_text(text, reply_markup=self.services.keyboards.build_main_menu_keyboard())

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        state = get_user_state(context)
        if not update.message or not update.message.text:
            return False
        if state.awaiting != "scan_target" and state.reels:
            return await self._handle_selection_text(update, context)
        if state.awaiting != "scan_target":
            return False

        target = self.services.resolver.normalize_page_url(update.message.text.strip())
        state.scan_target = target
        state.awaiting = None
        try:
            loading = await update.message.reply_text("🎮 Loading...\n▰▰▱▱▱ Mengambil page...")
            scraper = self.services.scraper_for_update(update)
            state.page_info = await scraper.fetch_page_info(target)
            session_status = await scraper.validate_session(target)
            await loading.edit_text("🎮 Loading...\n▰▰▰▰▱ Almost ready...")
            await update.message.reply_text(
                self.services.formatter.page_info_text(
                    state.page_info,
                    session_status="usable" if session_status.valid else "expired" if session_status.valid is False else "missing",
                ),
                reply_markup=self.services.keyboards.build_scan_order_keyboard(),
            )
        except Exception as exc:
            await update.message.reply_text(
                self.services.formatter.error_text(f"Scan gagal: {exc}"),
                reply_markup=self.services.keyboards.build_main_menu_keyboard(),
            )
        return True

    async def choose_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE, order: str) -> None:
        state = get_user_state(context)
        if not state.scan_target:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("Kirim URL halaman dulu.", reply_markup=self.services.keyboards.build_main_menu_keyboard())
            return
        if update.callback_query:
            await update.callback_query.answer()
            try:
                await update.callback_query.edit_message_text("🎮 Loading...\n▰▰▰▱▱ Mengambil reels...")
            except BadRequest as exc:
                if "Message is not modified" not in str(exc):
                    raise
        state.scan_order = order
        state.scan_mode = "pick" if order == "pick" else order
        state.scan_page = 1
        state.selected_indices.clear()
        try:
            reels = await self.services.scraper_for_update(update).fetch_reels(
                state.scan_target,
                order="newest" if order == "pick" else order,
                max_reels=None,
                use_browser_scroll=True,
            )
            state.reels = reels
            await self._show_page(update, context)
        except Exception as exc:
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    self.services.formatter.error_text(f"Popular reels gagal tampil: {exc}"),
                    reply_markup=self.services.keyboards.build_scan_order_keyboard(),
                )

    async def handle_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
        state = get_user_state(context)
        if not state.reels:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("Belum ada hasil scan.", reply_markup=self.services.keyboards.build_main_menu_keyboard())
            return
        if action == "next":
            state.scan_page += 1
        elif action == "prev":
            state.scan_page -= 1
        await self._show_page(update, context)

    async def toggle_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, slot: int) -> None:
        state = get_user_state(context)
        page_items, page, total_pages = paginate(state.reels, state.scan_page, state.scan_page_size)
        if 1 <= slot <= len(page_items):
            reel = page_items[slot - 1]
            if reel.scan_index in state.selected_indices:
                state.selected_indices.remove(reel.scan_index)
            else:
                state.selected_indices.add(reel.scan_index)
        else:
            if update.callback_query:
                await update.callback_query.answer()
            return
        await self._show_page(update, context)

    async def process_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        state = get_user_state(context)
        selected = [reel for reel in state.reels if reel.scan_index in state.selected_indices]
        if not selected and state.reels:
            selected = [state.reels[0]]
        if not selected:
            if update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text("Tidak ada reel yang dipilih.", reply_markup=self.services.keyboards.build_main_menu_keyboard())
            elif update.message:
                await update.message.reply_text("Tidak ada reel yang dipilih.", reply_markup=self.services.keyboards.build_main_menu_keyboard())
            return

        if update.callback_query:
            await update.callback_query.answer()
        for reel in selected:
            detail = await self.services.scraper_for_update(update).fetch_reel_detail(
                reel.reel_id or reel.url,
                source_url=reel.source_url or reel.url or state.scan_target,
            )
            state.last_detail = detail
            caption = self.services.formatter.download_caption(detail)
            work_dir = self.services.temp_dir_for_update(update) / (detail.reel_id or reel.reel_id or "reel")
            work_dir.mkdir(parents=True, exist_ok=True)
            temp_paths = []
            try:
                media_path = await self.services.downloader_for_update(update).prepare_cdn_result(detail, work_dir)
                temp_paths.append(media_path)
                success, reason = await self.services.media_sender.send_video_file(
                    context.bot,
                    update.effective_chat.id,
                    media_path,
                    caption,
                    reply_markup=self.services.keyboards.build_download_keyboard(),
                )
                if success:
                    continue
                part_dir = work_dir / "parts"
                parts = await self.services.downloader_for_update(update).split_video_by_size(
                    media_path,
                    part_dir,
                    self.services.media_sender.max_upload_bytes,
                )
                split_success, split_reason = await self.services.media_sender.send_video_parts(
                    context.bot,
                    update.effective_chat.id,
                    parts,
                    caption,
                    reply_markup=self.services.keyboards.build_download_keyboard(),
                )
                if split_success:
                    continue
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=self.services.formatter.error_text(f"{reason}; split juga gagal: {split_reason}"),
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
        await self._show_page(update, context, answer_callback=False)

    async def _show_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE, answer_callback: bool = True) -> None:
        state = get_user_state(context)
        page_items, page, total_pages = paginate(state.reels, state.scan_page, state.scan_page_size)
        state.scan_page = page
        selected_slots = {
            index + 1
            for index, reel in enumerate(page_items)
            if reel.scan_index in state.selected_indices
        }
        text = self.services.formatter.reel_list_text(
            page_items,
            page,
            total_pages,
            state.scan_mode,
            selected_slots=sorted(selected_slots),
        )
        keyboard = self.services.keyboards.build_scan_page_keyboard(
            selected_slots,
            page,
            total_pages,
            has_prev=page > 1,
            has_next=page < total_pages,
            item_count=len(page_items),
        )
        if update.callback_query:
            if answer_callback:
                try:
                    await update.callback_query.answer()
                except BadRequest as exc:
                    if "Query is too old" not in str(exc) and "query id is invalid" not in str(exc):
                        raise
            try:
                await update.callback_query.edit_message_text(text, reply_markup=keyboard)
            except BadRequest as exc:
                if "Message is not modified" not in str(exc):
                    raise
            return
        if update.message:
            await update.message.reply_text(text, reply_markup=keyboard)

    async def _handle_selection_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        state = get_user_state(context)
        raw = update.message.text.strip()
        if not raw:
            return False
        page_items, _, _ = paginate(state.reels, state.scan_page, state.scan_page_size)
        selected: list[Reel] = []
        if all(part.isdigit() for part in raw.split()):
            for part in raw.split():
                slot = int(part)
                if 1 <= slot <= len(page_items):
                    selected.append(page_items[slot - 1])
                else:
                    selected.extend([reel for reel in state.reels if reel.scan_index == slot])
            if not selected and raw.isdigit():
                detail = await self.services.scraper_for_update(update).fetch_reel_detail(raw)
                state.last_detail = detail
                fake_reel = Reel(id=raw, title=detail.title or raw, url=detail.source_url, source_url=detail.source_url, scan_index=1)
                state.reels = [fake_reel]
                state.selected_indices = {1}
                await self.process_selection(update, context)
                return True
            state.selected_indices = {reel.scan_index for reel in selected}
            await self.process_selection(update, context)
            return True
        return False
