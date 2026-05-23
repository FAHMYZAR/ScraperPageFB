from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

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
            banner_url = self.services.banner_url
            if banner_url:
                try:
                    await update.message.reply_photo(photo=banner_url)
                except TelegramError:
                    pass
            loading = await update.message.reply_text(self.services.formatter.loading_text("Loading...", final=False))
            try:
                await loading.edit_text(self.services.formatter.loading_text("Loading...", final=True))
            except TelegramError:
                pass
            await update.message.reply_text(text, reply_markup=self.services.keyboards.build_main_menu_keyboard(), parse_mode="HTML")
            return
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            await query.edit_message_text(text, reply_markup=self.services.keyboards.build_main_menu_keyboard(), parse_mode="HTML")

    async def exit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        state = get_user_state(context)
        state.clear()
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("Sesi menu ditutup. Ketik /start untuk membuka lagi.")
            return
        if update.message:
            await update.message.reply_text("Sesi menu ditutup. Ketik /start untuk membuka lagi.")
