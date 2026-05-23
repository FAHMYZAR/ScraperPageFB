from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urlunparse

import aiohttp

from CLI_Mode.facebook_reels_cli import DEFAULT_HEADERS


FACEBOOK_HOSTS = {
    "facebook.com",
    "www.facebook.com",
    "web.facebook.com",
    "m.facebook.com",
    "mobile.facebook.com",
    "fb.watch",
}


@dataclass(slots=True)
class FacebookUrlResolver:
    timeout_seconds: int = 20

    def is_facebook_video_url(self, raw_url: str) -> bool:
        parsed = urlparse(str(raw_url).strip())
        host = parsed.netloc.lower().removeprefix("www.")
        if host not in FACEBOOK_HOSTS:
            return False
        path = parsed.path.lower()
        return (
            host == "fb.watch"
            or "/reel/" in path
            or "/share/r/" in path
            or "/share/v/" in path
            or "/watch/" in path
            or "/videos/" in path
            or "video.php" in path
        )

    def normalize_url(self, raw_url: str) -> str:
        text = str(raw_url or "").strip()
        if not text:
            raise ValueError("URL kosong.")
        if not re.match(r"^https?://", text, flags=re.I):
            text = "https://" + text

        parsed = urlparse(text)
        host = parsed.netloc.lower()
        if host not in FACEBOOK_HOSTS and host.removeprefix("www.") not in FACEBOOK_HOSTS:
            raise ValueError("URL bukan Facebook.")
        host = "web.facebook.com" if host in {"facebook.com", "www.facebook.com", "m.facebook.com", "mobile.facebook.com"} else host

        reel_id = self.extract_reel_id(text)
        if reel_id:
            return f"https://web.facebook.com/reel/{reel_id}/"

        video_id = self.extract_video_id(text)
        if video_id:
            return f"https://web.facebook.com/watch/?v={video_id}"

        return urlunparse(("https", host, parsed.path or "/", "", parsed.query, ""))

    def normalize_page_url(self, raw_url: str) -> str:
        text = self.normalize_url(raw_url) if "/reel/" in raw_url or "/share/r/" in raw_url else str(raw_url).strip()
        parsed = urlparse(text if re.match(r"^https?://", text, re.I) else "https://" + text)
        host = parsed.netloc.lower()
        if host not in FACEBOOK_HOSTS and host.removeprefix("www.") not in FACEBOOK_HOSTS:
            raise ValueError("URL bukan Facebook.")
        host = "web.facebook.com" if host in {"facebook.com", "www.facebook.com", "m.facebook.com", "mobile.facebook.com"} else host
        path = parsed.path or "/"
        if "/reels" not in path.lower() and not path.endswith("/reels/"):
            path = path.rstrip("/") + "/reels/"
        return urlunparse(("https", host, path, "", parsed.query, ""))

    def extract_reel_id(self, raw_url: str) -> Optional[str]:
        text = str(raw_url or "")
        patterns = [
            r"/reel/(\d+)",
            r"/share/r/(\d+)",
            r"[?&]reel_id=(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def extract_video_id(self, raw_url: str) -> Optional[str]:
        text = str(raw_url or "")
        patterns = [
            r"[?&]v=(\d+)",
            r"/videos/(\d+)",
            r"/watch/.*?/(\d+)",
            r"[?&]video_id=(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    async def resolve_share_url(self, raw_url: str) -> str:
        normalized = self.normalize_url(raw_url)
        if "fb.watch" not in normalized and "/watch/" not in normalized and "/share/v/" not in normalized:
            return normalized

        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout, headers=DEFAULT_HEADERS) as session:
            async with session.get(normalized, allow_redirects=True) as response:
                final_url = str(response.url)
                return self.normalize_url(final_url)
