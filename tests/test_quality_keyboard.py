from bot.keyboards.menu_keyboard import MenuKeyboardFactory
from models import CdnResult, CdnVariant


def test_quality_keyboard_lists_video_variants():
    result = CdnResult(
        video_variants=[
            CdnVariant(url="u1", quality="720p", width=1280, height=720, bitrate=1000),
            CdnVariant(url="u2", quality="1080p", width=1920, height=1080, bitrate=2000),
        ]
    )

    keyboard = MenuKeyboardFactory().build_download_quality_keyboard(result)
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert "🎞 Best" in labels
    assert "720p" in labels
    assert "1080p" in labels
