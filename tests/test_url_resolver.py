from services.facebook_url_resolver import FacebookUrlResolver


def test_normalize_facebook_mobile_reel_url():
    resolver = FacebookUrlResolver()

    result = resolver.normalize_url("https://m.facebook.com/reel/1234567890/?mibextid=x")

    assert result == "https://web.facebook.com/reel/1234567890/"


def test_extract_reel_id_from_share_reel_url():
    resolver = FacebookUrlResolver()

    assert resolver.extract_reel_id("https://facebook.com/share/r/987654321/?x=y") == "987654321"


def test_share_video_url_is_accepted_for_redirect_resolution():
    resolver = FacebookUrlResolver()

    assert resolver.is_facebook_video_url("https://web.facebook.com/share/v/1DvBq25zgd/")
    assert resolver.normalize_url("https://web.facebook.com/share/v/1DvBq25zgd/") == "https://web.facebook.com/share/v/1DvBq25zgd/"


def test_validate_accepts_fb_watch_and_rejects_non_facebook():
    resolver = FacebookUrlResolver()

    assert resolver.is_facebook_video_url("https://fb.watch/abcDEF/")
    assert not resolver.is_facebook_video_url("https://example.com/reel/123")
