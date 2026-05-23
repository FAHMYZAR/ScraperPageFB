from __future__ import annotations

from typing import Iterable, List, Sequence, Set

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


class MenuKeyboardFactory:
    def build_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        rows = [
            [
                InlineKeyboardButton("🔐 Login", callback_data="menu:login"),
                InlineKeyboardButton("🕷 Scan", callback_data="menu:scan"),
            ],
            [
                InlineKeyboardButton("⬇ Download", callback_data="menu:download"),
                InlineKeyboardButton("🧾 Session", callback_data="menu:session"),
            ],
            [
                InlineKeyboardButton("🧹 Clear", callback_data="menu:clear"),
                InlineKeyboardButton("🏠 Home", callback_data="menu:home"),
            ],
        ]
        return InlineKeyboardMarkup(rows)

    def build_scan_order_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🔥 Popular", callback_data="scan:order:popular"),
                    InlineKeyboardButton("🎯 Pick Sendiri", callback_data="scan:order:pick"),
                ],
                [
                    InlineKeyboardButton("🔙 Back", callback_data="menu:home"),
                    InlineKeyboardButton("🏠 Home", callback_data="menu:home"),
                ],
            ]
        )

    def build_session_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Validasi", callback_data="session:validate"),
                    InlineKeyboardButton("🧹 Clear", callback_data="session:clear"),
                ],
                [
                    InlineKeyboardButton("🔙 Back", callback_data="menu:home"),
                    InlineKeyboardButton("🏠 Home", callback_data="menu:home"),
                ],
            ]
        )

    def build_download_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📎 Kirim URL", callback_data="download:prompt"),
                    InlineKeyboardButton("🏠 Home", callback_data="menu:home"),
                ],
            ]
        )

    def build_scan_page_keyboard(
        self,
        selected_slots: Set[int],
        page: int,
        total_pages: int,
        has_prev: bool,
        has_next: bool,
    ) -> InlineKeyboardMarkup:
        rows = [
            [
                InlineKeyboardButton("1" if 1 not in selected_slots else "1 ✅", callback_data="scan:select:1"),
                InlineKeyboardButton("2" if 2 not in selected_slots else "2 ✅", callback_data="scan:select:2"),
                InlineKeyboardButton("3" if 3 not in selected_slots else "3 ✅", callback_data="scan:select:3"),
            ],
            [
                InlineKeyboardButton("⬅ Prev", callback_data="scan:prev" if has_prev else "scan:noop"),
                InlineKeyboardButton("Next ➡", callback_data="scan:next" if has_next else "scan:noop"),
            ],
            [
                InlineKeyboardButton("✅ Process", callback_data="scan:process"),
                InlineKeyboardButton("🔙 Back", callback_data="menu:scan"),
            ],
            [
                InlineKeyboardButton("🏠 Home", callback_data="menu:home"),
            ],
        ]
        return InlineKeyboardMarkup(rows)

    def build_detail_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("⬇ Download", callback_data="download:prompt"),
                    InlineKeyboardButton("🔙 Back", callback_data="menu:scan"),
                ],
                [
                    InlineKeyboardButton("🏠 Home", callback_data="menu:home"),
                ],
            ]
        )

    def build_confirm_keyboard(self, yes_callback: str, no_callback: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Yes", callback_data=yes_callback),
                    InlineKeyboardButton("❌ No", callback_data=no_callback),
                ],
            ]
        )
