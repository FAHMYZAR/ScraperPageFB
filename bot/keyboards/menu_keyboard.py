from __future__ import annotations

from typing import Iterable, List, Sequence, Set

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from models import CdnResult


class MenuKeyboardFactory:
    def build_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        rows = [
            [
                InlineKeyboardButton("🔐 Login / Session", callback_data="menu:login"),
                InlineKeyboardButton("🕷 Scrape Reels", callback_data="menu:scan"),
            ],
            [
                InlineKeyboardButton("⬇ Download Video", callback_data="menu:download"),
                InlineKeyboardButton("🧾 Cek Session", callback_data="menu:session"),
            ],
            [
                InlineKeyboardButton("📄 Scrape Page JSON", callback_data="menu:text_scrape"),
                InlineKeyboardButton("🔗 Get Link JSON", callback_data="menu:text_link"),
            ],
            [
                InlineKeyboardButton("🧹 Clear Session", callback_data="menu:clear"),
                InlineKeyboardButton("🚪 Keluar", callback_data="menu:exit"),
            ],
        ]
        return InlineKeyboardMarkup(rows)

    def build_text_tools_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📄 Scrape Page JSON", callback_data="menu:text_scrape"),
                    InlineKeyboardButton("🔗 Get Link JSON", callback_data="menu:text_link"),
                ],
                [InlineKeyboardButton("🏠 Home", callback_data="menu:home")],
            ]
        )

    def build_login_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🌐 Login Browser", callback_data="login:browser"),
                    InlineKeyboardButton("🍪 Paste Cookie", callback_data="login:paste"),
                ],
                [
                    InlineKeyboardButton("📄 Upload Cookie JSON", callback_data="login:json"),
                    InlineKeyboardButton("📜 Upload Netscape Cookie", callback_data="login:netscape"),
                ],
                [
                    InlineKeyboardButton("🧹 Clear Session", callback_data="session:clear"),
                    InlineKeyboardButton("🔙 Back", callback_data="menu:home"),
                ],
                [InlineKeyboardButton("🏠 Home", callback_data="menu:home")],
            ]
        )

    def build_scan_order_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🔥 Popular", callback_data="scan:order:popular"),
                    InlineKeyboardButton("🆕 Terbaru", callback_data="scan:order:newest"),
                ],
                [
                    InlineKeyboardButton("📜 Dari Bawah / Lama", callback_data="scan:order:oldest"),
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
                    InlineKeyboardButton("⬇ Download Lagi", callback_data="download:prompt"),
                    InlineKeyboardButton("🏠 Home", callback_data="menu:home"),
                ],
            ]
        )

    def build_download_quality_keyboard(self, result: CdnResult) -> InlineKeyboardMarkup:
        rows: list[list[InlineKeyboardButton]] = [[InlineKeyboardButton("🎞 Best", callback_data="download:quality:best")]]
        variants = [variant for variant in result.video_variants if variant.url and not variant.is_audio_only]
        for index, variant in enumerate(variants[:12]):
            label = variant.quality or (f"{variant.height}p" if variant.height else "Video")
            if variant.width and variant.height and label != f"{variant.height}p":
                label = f"{label} {variant.width}x{variant.height}"
            rows.append([InlineKeyboardButton(label, callback_data=f"download:quality:{index}")])
        rows.append(
            [
                InlineKeyboardButton("⬇ Download Lagi", callback_data="download:prompt"),
                InlineKeyboardButton("🏠 Home", callback_data="menu:home"),
            ]
        )
        return InlineKeyboardMarkup(rows)

    def build_error_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🔁 Coba Lagi", callback_data="download:prompt"),
                    InlineKeyboardButton("⬇ Download Lagi", callback_data="download:prompt"),
                ],
                [InlineKeyboardButton("🏠 Home", callback_data="menu:home")],
            ]
        )

    def build_scan_page_keyboard(
        self,
        selected_slots: Set[int],
        page: int,
        total_pages: int,
        has_prev: bool,
        has_next: bool,
        item_count: int = 3,
    ) -> InlineKeyboardMarkup:
        def slot_button(slot: int) -> InlineKeyboardButton:
            if slot > item_count:
                return InlineKeyboardButton(str(slot), callback_data="scan:noop")
            label = str(slot) if slot not in selected_slots else f"{slot} ✅"
            return InlineKeyboardButton(label, callback_data=f"scan:select:{slot}")

        rows = [
            [
                slot_button(1),
                slot_button(2),
                slot_button(3),
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
