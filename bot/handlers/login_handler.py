from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.base import BotServices, get_user_state


class LoginHandler:
    def __init__(self, services: BotServices) -> None:
        self.services = services

    async def prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        state = get_user_state(context)
        state.awaiting = None
        text = "LOGIN / SESSION\n\nPilih metode login/session:"
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            await query.edit_message_text(text, reply_markup=self.services.keyboards.build_login_keyboard())
            return
        if update.message:
            await update.message.reply_text(text, reply_markup=self.services.keyboards.build_login_keyboard())

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        state = get_user_state(context)
        query = update.callback_query
        if query is None:
            return
        await query.answer()
        if data == "login:paste":
            state.awaiting = "cookie_login"
            await query.edit_message_text(
                "Kirim cookie string Facebook dalam satu pesan.\nFormat umum: c_user=...; xs=...; datr=...",
                reply_markup=self.services.keyboards.build_login_keyboard(),
            )
            return
        if data == "login:json":
            state.awaiting = "cookie_json"
            await query.edit_message_text("Upload file cookie JSON / storageState.", reply_markup=self.services.keyboards.build_login_keyboard())
            return
        if data == "login:netscape":
            state.awaiting = "cookie_netscape"
            await query.edit_message_text("Upload file Netscape cookie.", reply_markup=self.services.keyboards.build_login_keyboard())
            return
        if data == "login:browser":
            await query.edit_message_text("Mencoba import cookie dari browser lokal...", reply_markup=self.services.keyboards.build_login_keyboard())
            try:
                manager = self.services.session_for_update(update)
                await asyncio.to_thread(manager.import_browser_cookies, self.services.default_target)
                status = await self.services.scraper_for_update(update).validate_session(self.services.default_target)
                await query.edit_message_text(
                    self.services.formatter.session_status_text(status, storage_id=manager.storage_id),
                    reply_markup=self.services.keyboards.build_session_keyboard(),
                )
            except Exception as exc:
                await query.edit_message_text(
                    self.services.formatter.error_text(f"Login browser gagal: {exc}"),
                    reply_markup=self.services.keyboards.build_login_keyboard(),
                )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        state = get_user_state(context)
        if state.awaiting != "cookie_login" or not update.message or not update.message.text:
            return False

        raw_cookie = update.message.text.strip()
        state.awaiting = None
        try:
            manager = self.services.session_for_update(update)
            manager.import_cookie_string(raw_cookie)
            status = await self.services.scraper_for_update(update).validate_session(self.services.default_target)
            await update.message.reply_text(
                "✅ Session berhasil disimpan.\n\n" + self.services.formatter.session_status_text(status, storage_id=manager.storage_id),
                reply_markup=self.services.keyboards.build_session_keyboard(),
            )
        except Exception as exc:
            await update.message.reply_text(
                self.services.formatter.error_text(f"Login session gagal: {exc}"),
                reply_markup=self.services.keyboards.build_login_keyboard(),
            )
        return True

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        state = get_user_state(context)
        if state.awaiting not in {"cookie_json", "cookie_netscape"} or not update.message or not update.message.document:
            return False

        document = update.message.document
        suffix = Path(document.file_name or "cookie.txt").suffix or ".txt"
        temp_path = Path(tempfile.gettempdir()) / f"telegram_cookie_{update.effective_user.id if update.effective_user else 0}{suffix}"
        try:
            file = await context.bot.get_file(document.file_id)
            await file.download_to_drive(custom_path=str(temp_path))
            manager = self.services.session_for_update(update)
            manager.import_cookie_file(str(temp_path))
            status = await self.services.scraper_for_update(update).validate_session(self.services.default_target)
            state.awaiting = None
            await update.message.reply_text(
                "✅ Session berhasil disimpan.\n\n" + self.services.formatter.session_status_text(status, storage_id=manager.storage_id),
                reply_markup=self.services.keyboards.build_session_keyboard(),
            )
        except Exception as exc:
            await update.message.reply_text(
                self.services.formatter.error_text(f"Import cookie gagal: {exc}"),
                reply_markup=self.services.keyboards.build_login_keyboard(),
            )
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        return True
