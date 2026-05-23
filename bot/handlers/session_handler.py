from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.base import BotServices
from bot.handlers.base import get_user_state


class SessionHandler:
    def __init__(self, services: BotServices) -> None:
        self.services = services

    async def show(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        status = await self.services.scraper.validate_session(self.services.default_target)
        text = self.services.formatter.session_status_text(status)
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            await query.edit_message_text(text, reply_markup=self.services.keyboards.build_session_keyboard())
            return
        if update.message:
            await update.message.reply_text(text, reply_markup=self.services.keyboards.build_session_keyboard())

    async def clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.services.session_manager.clear()
        get_user_state(context).clear()
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            await query.edit_message_text("Session dibersihkan.", reply_markup=self.services.keyboards.build_main_menu_keyboard())
            return
        if update.message:
            await update.message.reply_text("Session dibersihkan.", reply_markup=self.services.keyboards.build_main_menu_keyboard())
