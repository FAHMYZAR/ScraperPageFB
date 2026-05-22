#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import tempfile
import time
from html import escape
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import facebook_reels_cli as fb_cli
from facebook_reels_cli import ReelsScraper, SessionStore, ensure_dir, normalize_scan_order
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from telegram_bot_config import Settings, load_settings
from telegram_bot_state import UserFlowState
from telegram_bot_ui import (
    build_clear_confirm_keyboard,
    build_confirm_keyboard,
    build_detail_keyboard,
    build_main_menu_keyboard,
    build_scan_order_keyboard,
    build_scan_result_keyboard,
    format_detail_text,
    format_main_menu_text,
    format_scan_results_text,
    format_session_status_text,
)
from telegram_media_pipeline import (
    build_video_track_options,
    choose_best_audio_track,
    choose_best_video_track,
    prepare_media_file,
    split_dash_tracks,
)

LOGGER = logging.getLogger("telegram_reels_bot")

AWAIT_COOKIE = "await_cookie"
AWAIT_SCAN_URL = "await_scan_url"
AWAIT_SCAN_LIMIT = "await_scan_limit"
AWAIT_INSPECT_REEL_ID = "await_inspect_reel_id"

VALID_REELS_URL = re.compile(r"^https?://", re.IGNORECASE)
REEL_ID_PATTERN = re.compile(r"/reel/(\d+)|\b(\d{6,})\b")


class ReelsTelegramBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._configure_paths()
        self.store = SessionStore(path=self.settings.session_file)
        self.scraper = ReelsScraper(
            self.store,
            target=self.settings.default_target,
            workers=self.settings.default_workers,
        )

    def _configure_paths(self) -> None:
        fb_cli.SESSION_FILE = self.settings.session_file
        fb_cli.APP_DIR = self.settings.output_dir.parent
        fb_cli.OUTPUT_DIR = self.settings.output_dir
        ensure_dir(fb_cli.APP_DIR)
        ensure_dir(fb_cli.OUTPUT_DIR)
        ensure_dir(self.settings.session_file.parent)

    def build_application(self) -> Application:
        app = ApplicationBuilder().token(self.settings.bot_token).build()
        app.add_handler(CommandHandler("start", self.handle_start))
        app.add_handler(CommandHandler("menu", self.handle_start))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        app.add_error_handler(self.handle_error)
        return app

    def run(self) -> None:
        app = self.build_application()
        app.run_polling(allowed_updates=Update.ALL_TYPES)

    async def is_admin(self, update: Update) -> bool:
        user = update.effective_user
        if user and user.id == self.settings.admin_user_id:
            return True

        denial = "❌ Akses ditolak. Bot ini hanya untuk admin."
        if update.callback_query:
            try:
                await update.callback_query.answer(denial, show_alert=True)
            except Exception:
                pass
        elif update.effective_message:
            await update.effective_message.reply_text(denial)
        return False

    @staticmethod
    def _state(context: ContextTypes.DEFAULT_TYPE) -> UserFlowState:
        flow = context.user_data.get("flow")
        if isinstance(flow, UserFlowState):
            return flow
        flow = UserFlowState()
        context.user_data["flow"] = flow
        return flow

    async def _render_control(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        state: UserFlowState,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> None:
        chat = update.effective_chat
        if chat is None:
            return

        if state.control_chat_id is None:
            state.control_chat_id = chat.id

        if state.control_message_id is not None:
            is_caption_mode = state.control_message_kind == "photo"
            try:
                if is_caption_mode and len(text) <= 1024:
                    await context.bot.edit_message_caption(
                        chat_id=state.control_chat_id,
                        message_id=state.control_message_id,
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                    )
                else:
                    await context.bot.edit_message_text(
                        chat_id=state.control_chat_id,
                        message_id=state.control_message_id,
                        text=text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=reply_markup,
                    )
                    state.control_message_kind = "text"
                return
            except BadRequest as exc:
                if "message is not modified" in str(exc).lower():
                    return
            except Exception:
                pass

        sent = await context.bot.send_message(
            chat_id=chat.id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
        state.set_control_message(chat.id, sent.message_id)
        state.control_message_kind = "text"

    async def _show_home(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        state: UserFlowState,
        force_banner: bool = False,
    ) -> None:
        state.awaiting = None
        if force_banner and update.effective_chat:
            if state.control_chat_id and state.control_message_id:
                try:
                    await context.bot.delete_message(
                        chat_id=state.control_chat_id,
                        message_id=state.control_message_id,
                    )
                except Exception:
                    pass

            sent = await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=self.settings.banner_url,
                caption=format_main_menu_text(),
                parse_mode="HTML",
                reply_markup=build_main_menu_keyboard(),
            )
            state.set_control_message(update.effective_chat.id, sent.message_id)
            state.control_message_kind = "photo"
            return

        await self._render_control(
            update,
            context,
            state,
            format_main_menu_text(),
            build_main_menu_keyboard(),
        )

    async def _run_blocking(self, task: Callable[[], Any]) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, task)

    async def _run_with_loading(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        state: UserFlowState,
        title: str,
        task: Callable[[], Any],
    ) -> Any:
        spinner = ["⏳", "⌛", "🌀", "🔄"]
        start = time.monotonic()
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, task)
        tick = 0

        while not future.done():
            elapsed = int(time.monotonic() - start)
            text = (
                f"<b>{spinner[tick % len(spinner)]} {escape(title)}</b>\n"
                f"Mohon tunggu... {elapsed}s"
            )
            await self._render_control(update, context, state, text)
            await asyncio.sleep(1.1)
            tick += 1

        return await future

    def _extract_reel_id(self, raw: str) -> Optional[str]:
        text = raw.strip()
        if text.isdigit():
            return text
        match = REEL_ID_PATTERN.search(text)
        if not match:
            return None
        return match.group(1) or match.group(2)

    def _scan_summary(self, state: UserFlowState) -> str:
        target = state.scan_draft.get("target", self.scraper.target)
        order = normalize_scan_order(str(state.scan_draft.get("order", "newest")))
        order_label = {
            "newest": "Terbaru",
            "oldest": "Paling Lama",
            "popular": "Paling Populer",
        }.get(order, "Terbaru")
        max_reels = state.scan_draft.get("max_reels")
        limit_text = "Semua" if max_reels is None else str(max_reels)
        return (
            "<b>Konfirmasi Scan</b>\n"
            f"🔗 Target: {escape(str(target))}\n"
            f"🧭 Urutan: {escape(order_label)}\n"
            f"📦 Jumlah: {escape(limit_text)} reel\n\n"
            "Klik lanjutkan untuk memulai scan."
        )

    async def _build_session_status_text(self) -> str:
        source = str(self.store.meta.get("source", "unknown"))
        cookies = len(self.store.cookie_records)
        account_name = str(self.store.meta.get("account_name", ""))
        account_id = str(self.store.meta.get("account_id", "")) or self.store.get_cookie_value("c_user")

        usable: Optional[bool] = None
        reel_count: Optional[int] = None
        error = ""

        if self.store.cookie_records:
            try:
                response = await self._run_blocking(lambda: self.scraper._request(self.scraper.target))
                if self.scraper._looks_like_login_form(response.text, response.url):
                    usable = False
                else:
                    cards = self.scraper._extract_cards(response.text)
                    reel_count = len(cards)
                    usable = True
                    if not account_name:
                        identity = await self._run_blocking(self.scraper.resolve_account_identity)
                        account_name = identity.get("name", "") or account_name
                        account_id = identity.get("id", "") or account_id
            except Exception as exc:
                error = str(exc)

        return format_session_status_text(
            source=source,
            cookie_count=cookies,
            account_name=account_name,
            account_id=account_id,
            usable=usable,
            reel_count=reel_count,
            error=error,
        )

    async def _show_scan_results(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        state: UserFlowState,
    ) -> None:
        if not state.last_scan_results:
            await self._render_control(
                update,
                context,
                state,
                "Belum ada hasil scan. Jalankan scan dulu dari menu.",
                build_main_menu_keyboard(),
            )
            return

        target = state.last_scan_target or str(state.scan_draft.get("target", self.scraper.target))
        order = str(state.scan_draft.get("order", "newest"))
        text = format_scan_results_text(state.last_scan_results, target_url=target, order_label=order)
        await self._render_control(
            update,
            context,
            state,
            text,
            build_scan_result_keyboard(state.last_scan_results),
        )

    def _build_media_options(self, detail: Dict[str, Any]) -> list[Dict[str, Any]]:
        renditions = detail.get("renditions", []) or []
        video_tracks, audio_tracks = split_dash_tracks(renditions)
        best_audio = choose_best_audio_track(audio_tracks)
        options: list[Dict[str, Any]] = []

        for option in build_video_track_options(video_tracks, limit=8):
            options.append(
                {
                    "label": option["label"],
                    "video_url": str(option["track"].get("base_url", "")).strip(),
                    "audio_url": str(best_audio.get("base_url", "")).strip() if best_audio else None,
                    "video_track": option["track"],
                    "audio_track": best_audio,
                    "mode": "dash_merge" if best_audio else "video_only",
                }
            )

        best_video = choose_best_video_track(video_tracks)
        best_cdn_url = str(detail.get("best_cdn_url", "")).strip()
        if not options and best_cdn_url:
            options.append(
                {
                    "label": "Best CDN",
                    "video_url": best_cdn_url,
                    "audio_url": None,
                    "video_track": best_video or {},
                    "audio_track": None,
                    "mode": "direct",
                }
            )

        return options

    async def _send_media_file_with_fallback(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        file_path: Path,
        caption: str,
        width: int = 0,
        height: int = 0,
    ) -> tuple[bool, str]:
        try:
            with file_path.open("rb") as handle:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=handle,
                    caption=caption,
                    parse_mode="HTML",
                    width=width or None,
                    height=height or None,
                    supports_streaming=True,
                )
            return True, "video"
        except TelegramError as exc_video:
            try:
                with file_path.open("rb") as handle:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=handle,
                        caption=caption,
                        parse_mode="HTML",
                    )
                return True, f"document_fallback:{exc_video}"
            except TelegramError as exc_doc:
                return False, f"video={exc_video}; document={exc_doc}"

    async def _send_selected_media(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        state: UserFlowState,
        option: Dict[str, Any],
    ) -> None:
        reel_id = str(state.last_detail.get("reel_id", "reel"))
        video_url = str(option.get("video_url", "")).strip()
        audio_url = option.get("audio_url")
        if audio_url:
            audio_url = str(audio_url).strip() or None

        if not video_url:
            await self._render_control(
                update,
                context,
                state,
                "⚠️ URL video tidak tersedia untuk opsi ini.",
                build_detail_keyboard(),
            )
            return

        headers = dict(fb_cli.DEFAULT_HEADERS)
        with tempfile.TemporaryDirectory(prefix="tg_media_") as tmp_dir:
            work_dir = Path(tmp_dir)
            try:
                media_path = await self._run_with_loading(
                    update,
                    context,
                    state,
                    f"Menyiapkan media {option.get('label', '')}",
                    lambda: prepare_media_file(
                        reel_id=reel_id,
                        video_url=video_url,
                        audio_url=audio_url,
                        work_dir=work_dir,
                        headers=headers,
                    ),
                )
            except Exception as exc:
                await self._render_control(
                    update,
                    context,
                    state,
                    (
                        "⚠️ Gagal menyiapkan file video+audio.\n"
                        f"Detail: <code>{escape(str(exc))}</code>"
                    ),
                    build_detail_keyboard(),
                )
                return

            video_track = option.get("video_track") or {}
            width = int(video_track.get("width", 0) or 0)
            height = int(video_track.get("height", 0) or 0)
            sent, mode = await self._send_media_file_with_fallback(
                context=context,
                chat_id=update.effective_chat.id,
                file_path=media_path,
                caption=(
                    f"🎬 Reel <code>{escape(reel_id)}</code>\n"
                    f"🏷️ Opsi: {escape(str(option.get('label', 'Best')))}"
                ),
                width=width,
                height=height,
            )

            if sent:
                await self._render_control(
                    update,
                    context,
                    state,
                    (
                        "✅ Media berhasil dikirim.\n"
                        f"Mode kirim: <code>{escape(mode)}</code>"
                    ),
                    build_detail_keyboard(
                        resolution_buttons=[
                            (f"🎞️ {opt['label']}", f"media:pick:{idx}")
                            for idx, opt in enumerate(state.media_options)
                        ],
                        show_send_best=bool(state.media_options),
                    ),
                )
            else:
                await self._render_control(
                    update,
                    context,
                    state,
                    (
                        "⚠️ Gagal kirim media ke Telegram.\n"
                        "Silakan pakai CDN URL berikut:\n"
                        f"<code>{escape(video_url)}</code>\n\n"
                        f"Detail: <code>{escape(mode)}</code>"
                    ),
                    build_detail_keyboard(
                        resolution_buttons=[
                            (f"🎞️ {opt['label']}", f"media:pick:{idx}")
                            for idx, opt in enumerate(state.media_options)
                        ],
                        show_send_best=bool(state.media_options),
                    ),
                )

    async def _show_detail_by_reel_id(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        state: UserFlowState,
        reel_id: str,
        source_url: Optional[str] = None,
    ) -> None:
        try:
            detail = await self._run_with_loading(
                update,
                context,
                state,
                f"Mengambil detail reel {reel_id}",
                lambda: self.scraper.fetch_reel_detail(reel_id, source_url=source_url),
            )
            await self._run_blocking(lambda: self.scraper.save_detail(detail))
        except Exception as exc:
            await self._render_control(
                update,
                context,
                state,
                (
                    "⚠️ Gagal mengambil detail reel.\n"
                    "Pastikan session Facebook valid lalu coba lagi.\n\n"
                    f"Detail: <code>{escape(str(exc))}</code>"
                ),
                build_detail_keyboard(),
            )
            return

        thumb = str(detail.get("thumbnail_url", "")).strip()
        if thumb.startswith("http"):
            try:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=thumb,
                    caption="🖼️ Preview reel",
                )
            except Exception:
                pass

        state.last_detail = detail
        state.media_options = self._build_media_options(detail)
        resolution_buttons = [
            (f"🎞️ {option['label']}", f"media:pick:{idx}")
            for idx, option in enumerate(state.media_options)
        ]
        await self._render_control(
            update,
            context,
            state,
            format_detail_text(detail),
            build_detail_keyboard(
                resolution_buttons=resolution_buttons,
                show_send_best=bool(state.media_options),
            ),
        )

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.is_admin(update):
            return

        state = self._state(context)
        await self._show_home(update, context, state, force_banner=True)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.is_admin(update):
            return

        query = update.callback_query
        if query is None:
            return

        state = self._state(context)
        if query.message:
            state.set_control_message(query.message.chat_id, query.message.message_id)
            state.control_message_kind = "photo" if query.message.photo else "text"

        await query.answer()
        data = query.data or ""

        if data == "menu:home":
            await self._show_home(update, context, state)
            return

        if data == "menu:exit":
            state.awaiting = None
            await self._render_control(
                update,
                context,
                state,
                "✅ Menu ditutup. Klik tombol untuk buka lagi.",
                InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🏠 Buka Menu", callback_data="menu:home")]]
                ),
            )
            return

        if data == "menu:login":
            state.awaiting = AWAIT_COOKIE
            await self._render_control(
                update,
                context,
                state,
                (
                    "<b>🔐 Login Session Facebook</b>\n"
                    "Paste cookie string Facebook kamu di chat ini.\n\n"
                    "Catatan: jangan forward ke orang lain."
                ),
                InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("◀ Batal", callback_data="menu:home")],
                        [InlineKeyboardButton("❌ Exit", callback_data="menu:exit")],
                    ]
                ),
            )
            return

        if data == "menu:scan":
            state.awaiting = AWAIT_SCAN_URL
            state.reset_scan_draft()
            await self._render_control(
                update,
                context,
                state,
                (
                    "<b>🔎 Scan Reels Page</b>\n"
                    "Kirim URL reels page yang ingin di-scan.\n"
                    "Contoh:\n"
                    "<code>https://web.facebook.com/nama.page/reels/</code>"
                ),
                InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("Gunakan Default Target", callback_data="scan:url:default")],
                        [InlineKeyboardButton("◀ Kembali", callback_data="menu:home")],
                    ]
                ),
            )
            return

        if data == "scan:url:default":
            state.scan_draft["target"] = self.scraper.target
            state.awaiting = None
            await self._render_control(
                update,
                context,
                state,
                (
                    "<b>Pilih Urutan Scan</b>\n"
                    f"Target: {escape(self.scraper.target)}"
                ),
                build_scan_order_keyboard(),
            )
            return

        if data.startswith("scan:order:"):
            if not state.scan_draft.get("target"):
                await self._render_control(
                    update,
                    context,
                    state,
                    "Target URL belum diisi. Masuk ke menu scan lagi.",
                    build_main_menu_keyboard(),
                )
                return

            order = data.rsplit(":", 1)[-1]
            state.scan_draft["order"] = normalize_scan_order(order)
            state.awaiting = AWAIT_SCAN_LIMIT
            await self._render_control(
                update,
                context,
                state,
                (
                    "<b>Masukkan Jumlah Reel</b>\n"
                    "Kirim angka (contoh: 5) atau ketik <code>all</code> untuk semua."
                ),
                InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("Semua Reel", callback_data="scan:limit:all")],
                        [InlineKeyboardButton("◀ Kembali", callback_data="menu:scan")],
                    ]
                ),
            )
            return

        if data == "scan:limit:all":
            state.scan_draft["max_reels"] = None
            state.awaiting = None
            await self._render_control(
                update,
                context,
                state,
                self._scan_summary(state),
                build_confirm_keyboard("scan:start", cancel_callback="menu:scan"),
            )
            return

        if data == "scan:start":
            target = str(state.scan_draft.get("target", "")).strip()
            order = normalize_scan_order(str(state.scan_draft.get("order", "newest")))
            max_reels = state.scan_draft.get("max_reels")
            if not target:
                await self._render_control(
                    update,
                    context,
                    state,
                    "Target URL belum valid. Silakan ulangi dari menu scan.",
                    build_main_menu_keyboard(),
                )
                return

            try:
                results = await self._run_with_loading(
                    update,
                    context,
                    state,
                    "Menjalankan scan reels",
                    lambda: self.scraper.scan_reels_page(
                        target_url=target,
                        max_reels=max_reels,
                        order=order,
                        use_browser_scroll=True,
                    ),
                )
            except Exception as exc:
                await self._render_control(
                    update,
                    context,
                    state,
                    (
                        "⚠️ Scan gagal.\n"
                        "Pastikan URL benar dan session Facebook masih valid.\n\n"
                        f"Detail: <code>{escape(str(exc))}</code>"
                    ),
                    build_main_menu_keyboard(),
                )
                return

            state.last_scan_results = results
            state.last_scan_target = target
            await self._show_scan_results(update, context, state)
            return

        if data == "scan:results":
            await self._show_scan_results(update, context, state)
            return

        if data.startswith("scan:pick:"):
            if not state.last_scan_results:
                await self._render_control(
                    update,
                    context,
                    state,
                    "Belum ada hasil scan aktif. Jalankan scan dulu.",
                    build_main_menu_keyboard(),
                )
                return

            try:
                index = int(data.rsplit(":", 1)[-1])
            except ValueError:
                index = -1

            if index < 0 or index >= len(state.last_scan_results):
                await self._render_control(
                    update,
                    context,
                    state,
                    "Nomor reel tidak valid.",
                    build_scan_result_keyboard(state.last_scan_results),
                )
                return

            item = state.last_scan_results[index]
            reel_id = str(item.get("reel_id", "")).strip()
            if not reel_id:
                await self._render_control(
                    update,
                    context,
                    state,
                    "Reel ID tidak tersedia pada item terpilih.",
                    build_scan_result_keyboard(state.last_scan_results),
                )
                return

            await self._show_detail_by_reel_id(
                update,
                context,
                state,
                reel_id=reel_id,
                source_url=str(item.get("url", "")).strip() or None,
            )
            return

        if data == "media:best":
            if not state.media_options:
                await self._render_control(
                    update,
                    context,
                    state,
                    "Tidak ada opsi media yang tersedia pada detail ini.",
                    build_detail_keyboard(),
                )
                return
            await self._send_selected_media(update, context, state, state.media_options[0])
            return

        if data.startswith("media:pick:"):
            if not state.media_options:
                await self._render_control(
                    update,
                    context,
                    state,
                    "Tidak ada opsi media yang tersedia pada detail ini.",
                    build_detail_keyboard(),
                )
                return
            try:
                option_index = int(data.rsplit(":", 1)[-1])
            except ValueError:
                option_index = -1

            if option_index < 0 or option_index >= len(state.media_options):
                await self._render_control(
                    update,
                    context,
                    state,
                    "Pilihan resolusi tidak valid.",
                    build_detail_keyboard(
                        resolution_buttons=[
                            (f"🎞️ {opt['label']}", f"media:pick:{idx}")
                            for idx, opt in enumerate(state.media_options)
                        ],
                        show_send_best=bool(state.media_options),
                    ),
                )
                return

            await self._send_selected_media(update, context, state, state.media_options[option_index])
            return

        if data == "menu:inspect":
            state.awaiting = AWAIT_INSPECT_REEL_ID
            await self._render_control(
                update,
                context,
                state,
                (
                    "<b>🧾 Inspect Reel by ID</b>\n"
                    "Kirim reel ID atau link reel Facebook."
                ),
                InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("◀ Kembali", callback_data="menu:home")],
                        [InlineKeyboardButton("❌ Exit", callback_data="menu:exit")],
                    ]
                ),
            )
            return

        if data == "menu:session":
            text = await self._build_session_status_text()
            await self._render_control(update, context, state, text, build_main_menu_keyboard())
            return

        if data == "menu:clear":
            await self._render_control(
                update,
                context,
                state,
                (
                    "<b>🗑️ Clear Session</b>\n"
                    "Session Facebook yang tersimpan akan dihapus. Lanjutkan?"
                ),
                build_clear_confirm_keyboard(),
            )
            return

        if data == "session:clear:yes":
            await self._run_blocking(self.store.clear)
            state.awaiting = None
            state.last_scan_results = []
            state.last_scan_target = ""
            state.last_detail = {}
            state.media_options = []
            await self._render_control(
                update,
                context,
                state,
                "✅ Session berhasil dihapus.",
                build_main_menu_keyboard(),
            )
            return

        await self._render_control(
            update,
            context,
            state,
            "Perintah tidak dikenali. Kembali ke menu utama.",
            build_main_menu_keyboard(),
        )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.is_admin(update):
            return

        message = update.effective_message
        if message is None or not message.text:
            return

        state = self._state(context)
        text = message.text.strip()

        if state.awaiting == AWAIT_COOKIE:
            try:
                await message.delete()
            except Exception:
                pass

            try:
                await self._run_blocking(lambda: self.store.import_cookie_string(text))
                state.awaiting = None
                status_text = await self._build_session_status_text()
                await self._render_control(
                    update,
                    context,
                    state,
                    "✅ Cookie string berhasil disimpan.\n\n" + status_text,
                    build_main_menu_keyboard(),
                )
            except Exception as exc:
                await self._render_control(
                    update,
                    context,
                    state,
                    (
                        "⚠️ Gagal import cookie string.\n"
                        f"Detail: <code>{escape(str(exc))}</code>"
                    ),
                    build_main_menu_keyboard(),
                )
            return

        if state.awaiting == AWAIT_SCAN_URL:
            if not VALID_REELS_URL.match(text) or "facebook.com" not in text.lower():
                await self._render_control(
                    update,
                    context,
                    state,
                    (
                        "URL tidak valid.\n"
                        "Gunakan URL Facebook reels, contoh:\n"
                        "<code>https://web.facebook.com/nama.page/reels/</code>"
                    ),
                )
                return

            state.scan_draft["target"] = text
            state.awaiting = None
            await self._render_control(
                update,
                context,
                state,
                f"<b>Pilih Urutan Scan</b>\nTarget: {escape(text)}",
                build_scan_order_keyboard(),
            )
            return

        if state.awaiting == AWAIT_SCAN_LIMIT:
            lower = text.lower()
            if lower in {"all", "semua", "0"}:
                state.scan_draft["max_reels"] = None
            else:
                try:
                    value = int(text)
                except ValueError:
                    await self._render_control(
                        update,
                        context,
                        state,
                        "Input jumlah tidak valid. Kirim angka atau ketik <code>all</code>.",
                    )
                    return
                if value <= 0:
                    state.scan_draft["max_reels"] = None
                else:
                    state.scan_draft["max_reels"] = value

            state.awaiting = None
            await self._render_control(
                update,
                context,
                state,
                self._scan_summary(state),
                build_confirm_keyboard("scan:start", cancel_callback="menu:scan"),
            )
            return

        if state.awaiting == AWAIT_INSPECT_REEL_ID:
            reel_id = self._extract_reel_id(text)
            if not reel_id:
                await self._render_control(
                    update,
                    context,
                    state,
                    "Reel ID tidak valid. Kirim angka ID atau link reel.",
                )
                return

            state.awaiting = None
            await self._show_detail_by_reel_id(update, context, state, reel_id=reel_id)
            return

        await self._render_control(
            update,
            context,
            state,
            (
                "Kamu belum memilih aksi.\n"
                "Klik tombol menu untuk mulai."
            ),
            build_main_menu_keyboard(),
        )

    async def handle_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        LOGGER.exception("Unhandled exception in bot handler", exc_info=context.error)

        if not isinstance(update, Update):
            return
        if update.effective_user is None or update.effective_user.id != self.settings.admin_user_id:
            return

        state = self._state(context)
        try:
            await self._render_control(
                update,
                context,
                state,
                (
                    "⚠️ Terjadi error internal.\n"
                    "Silakan coba lagi. Jika berulang, cek log container."
                ),
                build_main_menu_keyboard(),
            )
        except Exception:
            pass


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram wrapper for Facebook Reels scraper")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate required environment variables and exit",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except Exception as exc:
        print(f"[!] Config error: {exc}")
        return 1

    if args.check_config:
        print("[+] Config OK")
        print(f"    Admin ID  : {settings.admin_user_id}")
        print(f"    Session   : {settings.session_file}")
        print(f"    Output Dir: {settings.output_dir}")
        return 0

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    bot = ReelsTelegramBot(settings)
    bot.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
