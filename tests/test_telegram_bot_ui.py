import unittest

from telegram import InlineKeyboardMarkup

from telegram_bot_ui import (
    build_main_menu_keyboard,
    build_scan_result_keyboard,
    format_scan_results_text,
)


class TelegramBotUiTests(unittest.TestCase):
    def test_main_menu_keyboard_shape(self) -> None:
        keyboard = build_main_menu_keyboard()
        self.assertIsInstance(keyboard, InlineKeyboardMarkup)
        self.assertGreaterEqual(len(keyboard.inline_keyboard), 3)

    def test_scan_result_keyboard_contains_numbered_buttons(self) -> None:
        results = [
            {"reel_id": "101"},
            {"reel_id": "102"},
            {"reel_id": "103"},
        ]
        keyboard = build_scan_result_keyboard(results)
        labels = [btn.text for row in keyboard.inline_keyboard for btn in row]
        self.assertIn("1", labels)
        self.assertIn("2", labels)
        self.assertIn("3", labels)
        self.assertIn("◀ Kembali", labels)

    def test_format_scan_results_text_has_metrics(self) -> None:
        text = format_scan_results_text(
            [
                {
                    "reel_id": "1001",
                    "card_views": "10K",
                    "likes": 100,
                    "comments": 10,
                    "shares": 5,
                    "title": "Contoh judul reel",
                    "best_cdn_url": "https://cdn.example/video.mp4",
                }
            ],
            target_url="https://web.facebook.com/page/reels/",
            order_label="Terbaru",
        )
        self.assertIn("1001", text)
        self.assertIn("10K", text)
        self.assertIn("Terbaru", text)
        self.assertIn("https://web.facebook.com/page/reels/", text)
        self.assertIn("cdn.example", text)


if __name__ == "__main__":
    unittest.main()
