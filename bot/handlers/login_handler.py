from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.base import BotServices, get_user_state


class LoginHandler:
    def __init__(self, services: BotServices) -> None:
        self.services = services

    async def prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        state = get_user_state(context)
        state.awaiting = "cookie_login"
        text = (
            "Kirim cookie string Facebook kamu dalam satu pesan.\n"
            "Format umum: c_user=...; xs=...; datr=..."
        )
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            await query.edit_message_text(text, reply_markup=self.services.keyboards.build_main_menu_keyboard())
            return
        if update.message:
            await update.message.reply_text(text, reply_markup=self.services.keyboards.build_main_menu_keyboard())

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        state = get_user_state(context)
        if state.awaiting != "cookie_login" or not update.message or not update.message.text:
            return False

        raw_cookie = update.message.text.strip()
        state.awaiting = None
        try:
            self.services.session_manager.import_cookie_string(raw_cookie)
            status = await self.services.scraper.validate_session(self.services.default_target)
            await update.message.reply_text(
                self.services.formatter.session_status_text(status),
                reply_markup=self.services.keyboards.build_session_keyboard(),
            )
        except Exception as exc:
            await update.message.reply_text(
                self.services.formatter.error_text(f"Login session gagal: {exc}"),
                reply_markup=self.services.keyboards.build_main_menu_keyboard(),
            )
        return True
