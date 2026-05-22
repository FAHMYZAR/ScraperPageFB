import os
import tempfile
import unittest
from pathlib import Path

from telegram_bot_config import Settings, load_settings


class TelegramBotConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._backup = dict(os.environ)
        self._cwd = Path.cwd()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._backup)
        os.chdir(self._cwd)

    def test_load_settings_reads_required_values(self) -> None:
        os.environ["TELEGRAM_BOT_TOKEN"] = "dummy-token"
        os.environ["TELEGRAM_ADMIN_USER_ID"] = "1105877445"

        settings = load_settings()

        self.assertIsInstance(settings, Settings)
        self.assertEqual(settings.bot_token, "dummy-token")
        self.assertEqual(settings.admin_user_id, 1105877445)

    def test_load_settings_uses_defaults_for_optional_values(self) -> None:
        os.environ["TELEGRAM_BOT_TOKEN"] = "dummy-token"
        os.environ["TELEGRAM_ADMIN_USER_ID"] = "1105877445"

        settings = load_settings()

        self.assertTrue(settings.banner_url.startswith("http"))
        self.assertGreaterEqual(settings.default_workers, 1)
        self.assertIn("/reels/", settings.default_target)

    def test_load_settings_raises_without_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                os.environ["TELEGRAM_ADMIN_USER_ID"] = "1105877445"

                with self.assertRaises(ValueError):
                    load_settings()
            finally:
                os.chdir(self._cwd)

    def test_load_settings_reads_dotenv_file(self) -> None:
        os.environ.clear()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                Path(".env").write_text(
                    "TELEGRAM_BOT_TOKEN=dummy-from-dotenv\n"
                    "TELEGRAM_ADMIN_USER_ID=1105877445\n",
                    encoding="utf-8",
                )

                settings = load_settings()

                self.assertEqual(settings.bot_token, "dummy-from-dotenv")
                self.assertEqual(settings.admin_user_id, 1105877445)
            finally:
                os.chdir(self._cwd)


if __name__ == "__main__":
    unittest.main()
