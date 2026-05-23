from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.base import BotServices, get_user_state


class StartHandler:
    def __init__(self, services: BotServices) -> None:
        self.services = services

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        state = get_user_state(context)
        state.awaiting = None
        user = update.effective_user
        user_name = user.first_name if user and user.first_name else "User"
        text = self.services.formatter.home_menu_text(user_name)
        if update.message:
            await update.message.reply_text(text, reply_markup=self.services.keyboards.build_main_menu_keyboard(), parse_mode="HTML")
            return
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            await query.edit_message_text(text, reply_markup=self.services.keyboards.build_main_menu_keyboard(), parse_mode="HTML")
