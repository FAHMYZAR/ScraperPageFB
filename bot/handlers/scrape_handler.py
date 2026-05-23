from __future__ import annotations

from dataclasses import replace
from typing import List

from telegram import Update
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
        text = "Kirim URL halaman Facebook yang ingin dipindai."
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            await query.edit_message_text(text, reply_markup=self.services.keyboards.build_main_menu_keyboard())
            return
        if update.message:
            await update.message.reply_text(text, reply_markup=self.services.keyboards.build_main_menu_keyboard())

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        state = get_user_state(context)
        if state.awaiting != "scan_target" or not update.message or not update.message.text:
            return False

        target = update.message.text.strip()
        state.scan_target = target
        state.awaiting = None
        try:
            state.page_info = await self.services.scraper.fetch_page_info(target)
            await update.message.reply_text(
                self.services.formatter.page_info_text(state.page_info),
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
        state.scan_order = order
        state.scan_mode = "popular" if order == "popular" else "pick"
        state.scan_page = 1
        state.selected_indices.clear()
        reels = await self.services.scraper.fetch_reels(state.scan_target, order=order, max_reels=None, use_browser_scroll=True)
        state.reels = reels
        await self._show_page(update, context)

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
        await self._show_page(update, context)

    async def process_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        state = get_user_state(context)
        selected = [reel for reel in state.reels if reel.scan_index in state.selected_indices]
        if not selected and state.reels:
            selected = [state.reels[0]]
        if not selected:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("Tidak ada reel yang dipilih.", reply_markup=self.services.keyboards.build_main_menu_keyboard())
            return

        await update.callback_query.answer()
        for reel in selected:
            detail = await self.services.scraper.fetch_reel_detail(
                reel.reel_id or reel.url,
                source_url=reel.source_url or reel.url or state.scan_target,
            )
            state.last_detail = detail
            caption = self.services.formatter.download_caption(detail)
            work_dir = (self.services.session_manager.session_file.parent / "downloads")
            work_dir.mkdir(parents=True, exist_ok=True)
            if detail.best_url:
                try:
                    media_path = await self.services.downloader.prepare_final_mp4(
                        detail.reel_id or reel.reel_id or "reel",
                        detail.best_url,
                        detail.audio_url,
                        work_dir,
                    )
                    success, _ = await self.services.media_sender.send_video_file(
                        context.bot,
                        update.effective_chat.id,
                        media_path,
                        caption,
                    )
                    if success:
                        continue
                except Exception:
                    pass
                success, _ = await self.services.media_sender.send_video_url(
                    context.bot,
                    update.effective_chat.id,
                    detail.best_url,
                    caption,
                )
                if success:
                    continue
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"{reel.title}\n{detail.source_url or reel.source_url}")
        await self._show_page(update, context)

    async def _show_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        state = get_user_state(context)
        page_items, page, total_pages = paginate(state.reels, state.scan_page, state.scan_page_size)
        state.scan_page = page
        text = self.services.formatter.reel_list_text(page_items, page, total_pages, state.scan_mode)
        selected_slots = {
            index + 1
            for index, reel in enumerate(page_items)
            if reel.scan_index in state.selected_indices
        }
        keyboard = self.services.keyboards.build_scan_page_keyboard(
            selected_slots,
            page,
            total_pages,
            has_prev=page > 1,
            has_next=page < total_pages,
        )
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=keyboard)
            return
        if update.message:
            await update.message.reply_text(text, reply_markup=keyboard)
