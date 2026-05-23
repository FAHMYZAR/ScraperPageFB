from models import Reel
from services.facebook_scraper import FacebookScraper
from services.session_manager import SessionManager


def test_sort_reels_popular_uses_full_summary_metrics(tmp_path):
    scraper = FacebookScraper(SessionManager(tmp_path / "session.json"), "https://web.facebook.com/page/reels/", workers=1)
    reels = [
        Reel(id="a", title="A", views=10, likes=100, comments=0, shares=0, scan_index=1),
        Reel(id="b", title="B", views=1000, likes=1, comments=0, shares=0, scan_index=2),
        Reel(id="c", title="C", views=1000, likes=50, comments=0, shares=0, scan_index=3),
    ]

    sorted_reels = scraper._sort_reels(reels, "popular")

    assert [reel.id for reel in sorted_reels] == ["c", "b", "a"]
    assert [reel.scan_index for reel in sorted_reels] == [1, 2, 3]
