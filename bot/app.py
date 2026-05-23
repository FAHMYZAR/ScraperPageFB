from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.handlers import DownloadHandler, LoginHandler, ScrapeHandler, SessionHandler, StartHandler
from bot.handlers.base import BotServices
from bot.keyboards.menu_keyboard import MenuKeyboardFactory
from config import BotConfig, load_config
from services import FacebookScraper, MediaSender, SessionManager, VideoDownloader
from utils import Formatter


logger = logging.getLogger(__name__)


class BotApp:
    def __init__(self, config: Optional[BotConfig] = None) -> None:
        self.config = config or load_config()
        self.session_manager = SessionManager(self.config.session_file)
        self.formatter = Formatter()
        self.keyboards = MenuKeyboardFactory()
        self.scraper = FacebookScraper(self.session_manager, self.config.default_target, self.config.default_workers)
        self.downloader = VideoDownloader(self.session_manager)
        self.media_sender = MediaSender()
        self.services = BotServices(
            session_manager=self.session_manager,
            scraper=self.scraper,
            downloader=self.downloader,
            media_sender=self.media_sender,
            formatter=self.formatter,
            keyboards=self.keyboards,
            default_target=self.config.default_target,
        )
        self.start_handler = StartHandler(self.services)
        self.login_handler = LoginHandler(self.services)
        self.scrape_handler = ScrapeHandler(self.services)
        self.download_handler = DownloadHandler(self.services)
        self.session_handler = SessionHandler(self.services)

    def build_application(self) -> Application:
        application = ApplicationBuilder().token(self.config.bot_token).build()
        application.add_handler(CommandHandler("start", self.handle_start))
        application.add_handler(CommandHandler("menu", self.handle_start))
        application.add_handler(CallbackQueryHandler(self.handle_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        application.add_error_handler(self.handle_error)
        return application

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.start_handler.handle(update, context)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            return
        data = query.data or ""

        if data in {"menu:home", "home"}:
            await self.start_handler.handle(update, context)
            return
        if data == "menu:login":
            await self.login_handler.prompt(update, context)
            return
        if data == "menu:scan":
            await self.scrape_handler.prompt_target(update, context)
            return
        if data == "menu:download":
            await self.download_handler.prompt(update, context)
            return
        if data == "menu:session":
            await self.session_handler.show(update, context)
            return
        if data == "menu:clear":
            await self.session_handler.clear(update, context)
            return
        if data == "session:validate":
            await self.session_handler.show(update, context)
            return
        if data == "session:clear":
            await self.session_handler.clear(update, context)
            return
        if data == "download:prompt":
            await self.download_handler.prompt(update, context)
            return
        if data == "scan:order:popular":
            await self.scrape_handler.choose_order(update, context, "popular")
            return
        if data == "scan:order:pick":
            await self.scrape_handler.choose_order(update, context, "newest")
            return
        if data == "scan:next":
            await self.scrape_handler.handle_navigation(update, context, "next")
            return
        if data == "scan:prev":
            await self.scrape_handler.handle_navigation(update, context, "prev")
            return
        if data.startswith("scan:select:"):
            try:
                slot = int(data.rsplit(":", 1)[-1])
            except ValueError:
                slot = 1
            await self.scrape_handler.toggle_selection(update, context, slot)
            return
        if data == "scan:process":
            await self.scrape_handler.process_selection(update, context)
            return
        if data == "scan:noop":
            await query.answer()
            return

        await query.answer()
        await query.edit_message_text("Perintah tidak dikenal.", reply_markup=self.keyboards.build_main_menu_keyboard())

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self.login_handler.handle_text(update, context):
            return
        if await self.scrape_handler.handle_text(update, context):
            return
        if await self.download_handler.handle_text(update, context):
            return
        if update.message:
            await update.message.reply_text("Gunakan menu /start untuk memulai.", reply_markup=self.keyboards.build_main_menu_keyboard())

    async def handle_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Telegram bot error", exc_info=context.error)

    def run(self) -> None:
        application = self.build_application()
        application.run_polling(allowed_updates=Update.ALL_TYPES)
