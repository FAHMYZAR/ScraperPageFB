from datetime import datetime

from models import PageInfo, SessionStatus
from models import Reel
from utils.formatter import Formatter


def test_caption_has_no_title_or_description_labels():
    formatter = Formatter()

    caption = formatter.caption("Judul", "Deskripsi")

    assert caption == "Judul\n\nDeskripsi"
    assert "Title:" not in caption
    assert "Description:" not in caption


def test_session_status_uses_required_labels_without_sensitive_values():
    formatter = Formatter()
    status = SessionStatus(
        available=True,
        valid=True,
        source="cookie_string",
        account_name="Akun",
        account_id="123456789",
        cookie_count=14,
        last_checked_at="20260523_120000",
    )

    text = formatter.session_status_text(status, storage_id="user-42")

    assert "SESSION STATUS" in text
    assert "Session test : usable" in text
    assert "Cookies      : 14" in text
    assert "cookie_string" in text
    assert "c_user" not in text


def test_page_info_includes_detected_cards_and_session_status():
    formatter = Formatter()
    page = PageInfo(name="Snow", title="Snow Reels", url="https://web.facebook.com/Snow/reels/", total_items=15, total_reels=15, detected_cards=15)

    text = formatter.page_info_text(page, session_status="usable")

    assert "Nama page" in text
    assert "Total reel cards detected : 15" in text
    assert "Status session" in text


def test_reel_list_shows_choiced_number_when_selected():
    formatter = Formatter()

    text = formatter.reel_list_text(
        [Reel(id="1", title="Judul", scan_index=1)],
        page=1,
        total_pages=1,
        mode="popular",
        selected_slots=[1],
    )

    assert "Choiced number 1" in text
