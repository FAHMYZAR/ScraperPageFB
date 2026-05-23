#!/usr/bin/env python3
"""
Facebook Reels CLI scraper.

Layer 1:
- scan reels page
- fetch each reel summary in parallel
- show title, description, likes, comments, shares

Layer 2:
- choose one reel ID
- fetch full reel payload
- extract DASH renditions and highest quality CDN URL

Session:
- imported from cookie string, JSON, or Netscape cookie file
- saved locally so the next run can reuse it
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import textwrap
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from getpass import getpass
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup
from requests.cookies import RequestsCookieJar, create_cookie

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

try:
    import browser_cookie3
except ImportError:
    browser_cookie3 = None

BASE_URL = "https://web.facebook.com"
DEFAULT_TARGET = "https://web.facebook.com/spaceshift95/reels/"
APP_DIR = Path("fb_reels_cli")
OUTPUT_DIR = APP_DIR / "output"
SESSION_FILE = APP_DIR / "session.json"
DEFAULT_WORKERS = 4
DEFAULT_LOGIN_TIMEOUT = 300
DEFAULT_LOGIN_POLL = 5
PLAYWRIGHT_BROWSER_CHANNELS = ("chrome", "msedge")
LOGIN_BROWSER_SOURCES = ("edge", "firefox", "chrome", "chromium", "brave", "opera")
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def clean_text(text: Any) -> str:
    return str(text or "").replace("\xa0", " ").strip()


def truncate(text: Any, width: int = 120) -> str:
    return textwrap.shorten(clean_text(text), width=width, placeholder="...")


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_compact_count(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value

    text = clean_text(value).lower()
    if not text:
        return None

    text = text.replace(" ", "")
    multipliers = [
        ("rb", 1_000),
        ("k", 1_000),
        ("m", 1_000_000),
        ("b", 1_000_000_000),
        ("jt", 1_000_000),
        ("juta", 1_000_000),
    ]

    for suffix, multiplier in multipliers:
        if text.endswith(suffix):
            number_part = text[: -len(suffix)].replace(",", ".")
            try:
                return int(float(number_part) * multiplier)
            except ValueError:
                return None

    digits_only = re.sub(r"[^0-9]", "", text)
    return safe_int(digits_only)


def format_metric(value: Optional[int], raw: Any = "") -> str:
    raw_text = clean_text(raw)
    if raw_text:
        if re.fullmatch(r"\d+", raw_text):
            return f"{int(raw_text):,}"
        return raw_text
    if value is None:
        return "-"
    return f"{value:,}"


def decode_js_escaped(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    try:
        decoded = json.loads('"' + text + '"')
    except Exception:
        decoded = bytes(text, "utf-8").decode("unicode_escape", errors="ignore")
    return decoded.replace("\\/", "/")


def first_group(text: str, patterns: List[str]) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def normalize_script_text(text: str) -> str:
    return text.replace('\\"', '"')


def safe_filename(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", clean_text(text))
    return cleaned.strip("_") or "reel"


def normalize_scan_order(choice: str) -> str:
    mapping = {
        "1": "newest",
        "2": "oldest",
        "3": "popular",
        "newest": "newest",
        "oldest": "oldest",
        "popular": "popular",
    }
    return mapping.get(clean_text(choice).lower(), "newest")


def parse_cookie_string_records(raw_cookie: str) -> List[Dict[str, Any]]:
    parsed: Dict[str, Dict[str, Any]] = {}
    cookie_text = clean_text(raw_cookie)
    if cookie_text.lower().startswith("cookie:"):
        cookie_text = cookie_text.split(":", 1)[1].strip()

    for chunk in cookie_text.split(";"):
        part = chunk.strip()
        if not part or "=" not in part:
            continue

        name, value = part.split("=", 1)
        name = clean_text(name)
        if not name:
            continue

        parsed[name] = {
            "name": name,
            "value": value.strip(),
            "domain": ".facebook.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
        }

    return list(parsed.values())


def extract_facebook_profile_name(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: List[str] = []

    current_user_match = re.search(r'"CurrentUserInitialData",\[\],\{.*?"NAME":"((?:\\.|[^"\\])*)"', html, flags=re.S)
    if current_user_match:
        current_user_name = clean_text(decode_js_escaped(current_user_match.group(1)))
        if current_user_name:
            return current_user_name

    for selector in (
        'meta[property="og:title"]',
        'meta[property="twitter:title"]',
        'meta[name="title"]',
    ):
        tag = soup.select_one(selector)
        if tag and tag.get("content"):
            candidates.append(clean_text(tag.get("content")))

    if soup.title and soup.title.string:
        candidates.append(clean_text(soup.title.string))

    for candidate in candidates:
        normalized = re.sub(r"\s*[|\-]\s*Facebook.*$", "", candidate, flags=re.IGNORECASE)
        normalized = re.sub(r"^\(\d+\)\s*", "", normalized)
        normalized = clean_text(normalized)
        if normalized and normalized.lower() not in {"facebook", "meta"}:
            return normalized

    return None


def build_login_url(target_url: str) -> str:
    return f"{BASE_URL}/login.php?next={quote(target_url, safe='')}"


def cookiejar_to_records(cookiejar: Any, default_domain: str = ".facebook.com") -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    if not cookiejar:
        return records

    for cookie in cookiejar:
        name = getattr(cookie, "name", "")
        if not name:
            continue

        rest = getattr(cookie, "_rest", {}) or {}
        http_only = bool(
            rest.get("HttpOnly")
            or rest.get("httponly")
            or rest.get("HTTPOnly")
            or getattr(cookie, "has_nonstandard_attr", lambda *_: False)("HttpOnly")
        )

        records.append(
            {
                "name": name,
                "value": getattr(cookie, "value", ""),
                "domain": getattr(cookie, "domain", None) or default_domain,
                "path": getattr(cookie, "path", None) or "/",
                "expires": getattr(cookie, "expires", None),
                "secure": bool(getattr(cookie, "secure", True)),
                "httpOnly": http_only,
                "sameSite": rest.get("SameSite") or rest.get("samesite") or getattr(cookie, "sameSite", None),
            }
        )

    return records


def has_browser_login_cookies(records: List[Dict[str, Any]]) -> bool:
    names = {clean_text(record.get("name")) for record in records}
    return "c_user" in names and "xs" in names


def load_browser_cookie_records(domain_name: str = "facebook.com") -> tuple[str, List[Dict[str, Any]]]:
    if browser_cookie3 is None:
        raise RuntimeError(
            "browser-cookie3 is not installed. Run: python -m pip install browser-cookie3"
        )

    last_errors: List[str] = []
    for browser_name in LOGIN_BROWSER_SOURCES:
        loader = getattr(browser_cookie3, browser_name, None)
        if loader is None:
            continue

        try:
            cookiejar = loader(domain_name=domain_name)
            records = cookiejar_to_records(cookiejar)
        except Exception as exc:
            last_errors.append(f"{browser_name}: {exc}")
            continue

        if records:
            return browser_name, records

    details = "; ".join(last_errors) if last_errors else "no supported browser cookies were found"
    raise RuntimeError(f"No Facebook cookies found in local browser profiles ({details})")


def login_via_browser(
    store: "SessionStore",
    scraper: "ReelsScraper",
    target_url: str = DEFAULT_TARGET,
    timeout: int = DEFAULT_LOGIN_TIMEOUT,
    poll_interval: int = DEFAULT_LOGIN_POLL,
) -> None:
    if browser_cookie3 is None:
        raise RuntimeError(
            "browser-cookie3 is not installed. Run: python -m pip install browser-cookie3"
        )

    login_url = build_login_url(target_url)
    timeout = max(1, timeout)
    poll_interval = max(1, poll_interval)

    print(f"[*] Opening browser login page: {login_url}")
    try:
        webbrowser.open(login_url, new=1, autoraise=True)
    except Exception:
        webbrowser.open(login_url)

    print("[*] Log in in the opened browser. I will auto-save the session once valid cookies appear.")
    started_at = time.monotonic()
    deadline = started_at + timeout
    last_status = ""

    while time.monotonic() < deadline:
        elapsed = int(time.monotonic() - started_at)
        print(f"[*] Waiting for login session... {elapsed}s/{timeout}s")

        status = ""
        try:
            browser_name, records = load_browser_cookie_records("facebook.com")
            if has_browser_login_cookies(records):
                temp_store = SessionStore(path=store.path)
                temp_store.cookie_records = records
                temp_store.meta = {
                    "source": f"browser_login:{browser_name}",
                    "browser": browser_name,
                    "login_url": login_url,
                    "updated_at": now_stamp(),
                }

                test_scraper = ReelsScraper(temp_store, target=target_url, workers=scraper.workers)
                response = test_scraper._request(target_url)
                cards = test_scraper._extract_cards(response.text)

                if not test_scraper._looks_like_login_form(response.text, response.url) and cards:
                    store.cookie_records = records
                    store.meta = temp_store.meta
                    store.save()
                    print(f"[+] Login captured from {browser_name} and saved to {store.path}")
                    print(f"[+] Session test: {len(cards)} reel cards detected")
                    return
                status = f"{browser_name}: cookies found but session is not ready yet"
            else:
                status = f"{browser_name}: browser cookies found but login cookies are incomplete"
        except Exception as exc:
            status = str(exc)

        if status and status != last_status:
            print(f"[*] {status}")
            last_status = status

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval, max(1, int(remaining))))

    raise TimeoutError(
        f"Timed out after {timeout} seconds waiting for browser login. "
        "Make sure the browser is signed in to Facebook and try again."
    )


class SessionStore:
    def __init__(self, path: Path = SESSION_FILE) -> None:
        self.path = Path(path)
        self.cookie_records: List[Dict[str, Any]] = []
        self.meta: Dict[str, Any] = {}
        self.load()

    def load(self) -> bool:
        if not self.path.exists():
            return False

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[!] Failed to load session file: {exc}")
            return False

        self.cookie_records = self._records_from_payload(payload)
        self.meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        return bool(self.cookie_records)

    def save(self) -> None:
        ensure_dir(self.path.parent)
        payload = {
            "saved_at": now_stamp(),
            "meta": self.meta,
            "cookies": self.cookie_records,
        }
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def clear(self) -> None:
        self.cookie_records = []
        self.meta = {}
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def describe(self) -> str:
        source = self.meta.get("source", "unknown")
        account_name = clean_text(self.meta.get("account_name", ""))
        account_id = clean_text(self.meta.get("account_id", ""))
        if not account_id:
            account_id = clean_text(self.get_cookie_value("c_user"))

        account_line = ""
        if account_name or account_id:
            account_line = f"Account     : {account_name or '-'}"
            if account_id:
                account_line += f" ({account_id})"
            account_line += "\n"

        return (
            f"Session file: {self.path}\n"
            f"Cookies     : {len(self.cookie_records)}\n"
            f"Source      : {source}\n"
            f"{account_line}"
            f"Saved       : {self.path.exists()}"
        )

    def get_cookie_value(self, name: str) -> str:
        for record in self.cookie_records:
            if clean_text(record.get("name")) == name:
                return clean_text(record.get("value"))
        return ""

    def _records_from_payload(self, payload: Any) -> List[Dict[str, Any]]:
        raw: Any = payload
        if isinstance(payload, dict):
            if "cookies" in payload:
                raw = payload["cookies"]
            elif all(isinstance(v, str) for v in payload.values()):
                raw = [
                    {
                        "name": key,
                        "value": value,
                        "domain": ".facebook.com",
                        "path": "/",
                    }
                    for key, value in payload.items()
                ]
            else:
                raw = []

        if not isinstance(raw, list):
            return []

        records: List[Dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name:
                continue
            records.append(
                {
                    "name": name,
                    "value": item.get("value", ""),
                    "domain": item.get("domain") or ".facebook.com",
                    "path": item.get("path") or "/",
                    "expires": item.get("expires"),
                    "secure": bool(item.get("secure", True)),
                    "httpOnly": bool(item.get("httpOnly", True)),
                    "sameSite": item.get("sameSite"),
                }
            )
        return self._dedupe_records(records)

    def _dedupe_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        deduped: List[Dict[str, Any]] = []
        for record in records:
            key = (record.get("name"), record.get("domain"), record.get("path"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(record)
        return deduped

    def import_cookie_records(
        self,
        records: List[Dict[str, Any]],
        source: str,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        cleaned: List[Dict[str, Any]] = []
        for item in records:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name:
                continue
            cleaned.append(
                {
                    "name": name,
                    "value": item.get("value", ""),
                    "domain": item.get("domain") or ".facebook.com",
                    "path": item.get("path") or "/",
                    "expires": item.get("expires"),
                    "secure": bool(item.get("secure", True)),
                    "httpOnly": bool(item.get("httpOnly", True)),
                    "sameSite": item.get("sameSite"),
                }
            )

        cleaned = self._dedupe_records(cleaned)
        if not cleaned:
            raise ValueError("No cookies were parsed from the input.")

        self.cookie_records = cleaned
        self.meta = {
            "source": source,
            "updated_at": now_stamp(),
        }
        if extra_meta:
            self.meta.update(extra_meta)
        self.save()

    def import_cookie_string(self, raw_cookie: str) -> None:
        records = parse_cookie_string_records(raw_cookie)

        if not records:
            cookie_text = clean_text(raw_cookie)
            if cookie_text.lower().startswith("cookie:"):
                cookie_text = cookie_text.split(":", 1)[1].strip()

            cookie = SimpleCookie()
            cookie.load(cookie_text)

            for name, morsel in cookie.items():
                records.append(
                    {
                        "name": name,
                        "value": morsel.value,
                        "domain": ".facebook.com",
                        "path": "/",
                        "secure": True,
                        "httpOnly": True,
                    }
                )

        self.import_cookie_records(records, "cookie_string")

    def import_cookie_file(self, file_path: str) -> None:
        path = Path(file_path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        stripped = text.lstrip()

        if stripped.startswith("{") or stripped.startswith("["):
            payload = json.loads(text)
            records = self._records_from_payload(payload)
            self.import_cookie_records(records, "json_file", {"file": str(path)})
        elif "# Netscape HTTP Cookie File" in text or "\t" in text:
            records = self._parse_netscape_cookie_text(text)
            self.import_cookie_records(records, "netscape_cookie_file", {"file": str(path)})
        else:
            self.import_cookie_string(text)
            self.meta.update({"file": str(path)})

        self.save()

    def _parse_netscape_cookie_text(self, text: str) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, include_subdomains, path, secure_flag, expires, name, value = parts[:7]
            records.append(
                {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": path,
                    "expires": safe_int(expires),
                    "secure": secure_flag.upper() == "TRUE",
                    "httpOnly": True,
                }
            )
        return self._dedupe_records(records)

    def build_requests_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        jar = RequestsCookieJar()

        for record in self.cookie_records:
            jar.set_cookie(
                create_cookie(
                    name=record.get("name", ""),
                    value=str(record.get("value", "")),
                    domain=record.get("domain") or ".facebook.com",
                    path=record.get("path") or "/",
                    secure=bool(record.get("secure", True)),
                    expires=record.get("expires"),
                )
            )

        session.cookies = jar
        return session


class ReelsScraper:
    def __init__(
        self,
        store: SessionStore,
        target: str = DEFAULT_TARGET,
        workers: int = DEFAULT_WORKERS,
    ) -> None:
        self.store = store
        self.target = target
        self.workers = max(1, workers)
        self.last_scan: List[Dict[str, Any]] = []
        ensure_dir(APP_DIR)
        ensure_dir(OUTPUT_DIR)

    def _session(self) -> requests.Session:
        return self.store.build_requests_session()

    def _request(self, url: str, timeout: int = 30) -> requests.Response:
        session = self._session()
        try:
            response = session.get(url, timeout=timeout, allow_redirects=True)
            return response
        except requests.RequestException as exc:
            raise RuntimeError(f"Request failed for {url}: {exc}") from exc

    def _looks_like_login_form(self, html: str, final_url: str) -> bool:
        if "login.php" in final_url or "/recover/initiate" in final_url:
            return True
        lower = html.lower()
        if re.search(r'name=["\']email["\']', lower) and re.search(r'name=["\']pass["\']', lower):
            return True
        if "email address or phone number" in lower and "log in to facebook" in lower:
            return True
        if "forgotten account" in lower and "password" in lower and "create new account" in lower:
            return True
        return False

    def _get_script_candidates(self, html: str, reel_id: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        candidates: List[str] = []

        for script in soup.find_all("script"):
            text = script.string or script.get_text() or ""
            normalized = normalize_script_text(text)
            score = 0
            if reel_id and reel_id in normalized:
                score += 2
            if "manifest_xml" in normalized:
                score += 6
            if (
                "playable_url_quality_hd" in normalized
                or "playable_url" in normalized
                or "hd_src" in normalized
                or "sd_src" in normalized
            ):
                score += 5
            if "videoDeliveryResponseResult" in normalized:
                score += 4
            for needle in ("message", "likers", "total_comment_count", "aggregated_reaction_count", "aggregated_comment_count"):
                if needle in normalized:
                    score += 1
            if score:
                candidates.append((score, len(normalized), normalized))

        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in candidates]

    def _merge_reel_payloads(self, base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
        if not base:
            return extra

        if extra.get("title") and not base.get("title"):
            base["title"] = extra["title"]
        if extra.get("description") and not base.get("description"):
            base["description"] = extra["description"]
        if extra.get("likes") is not None and base.get("likes") is None:
            base["likes"] = extra["likes"]
            base["likes_raw"] = extra.get("likes_raw", base.get("likes_raw", ""))
        if extra.get("comments") is not None and base.get("comments") is None:
            base["comments"] = extra["comments"]
            base["comments_raw"] = extra.get("comments_raw", base.get("comments_raw", ""))
        if extra.get("shares") is not None and base.get("shares") is None:
            base["shares"] = extra["shares"]
            base["shares_raw"] = extra.get("shares_raw", base.get("shares_raw", ""))
        if extra.get("thumbnail_url") and not base.get("thumbnail_url"):
            base["thumbnail_url"] = extra["thumbnail_url"]
        if extra.get("duration_seconds") is not None and base.get("duration_seconds") is None:
            base["duration_seconds"] = extra["duration_seconds"]

        if extra.get("best_cdn_url") and not base.get("best_cdn_url"):
            base["best_cdn_url"] = extra["best_cdn_url"]
            base["best_cdn_quality"] = extra.get("best_cdn_quality", base.get("best_cdn_quality", ""))
            base["best_cdn_bandwidth"] = extra.get("best_cdn_bandwidth", base.get("best_cdn_bandwidth", 0))
            base["renditions"] = extra.get("renditions", base.get("renditions", []))
            base["manifest_count"] = extra.get("manifest_count", base.get("manifest_count", 0))

        if base.get("status") == "partial" and extra.get("status") == "ok":
            base["status"] = "ok"

        return base

    def _parse_reel_payload_from_html(
        self,
        html: str,
        reel_id: str,
        card_views: str = "",
        source_url: str = "",
    ) -> Dict[str, Any]:
        candidates = self._get_script_candidates(html, reel_id)
        if not candidates:
            candidates = [normalize_script_text(html)]

        payload: Dict[str, Any] = {}
        for index, script_text in enumerate(candidates):
            parsed = self._parse_reel_blob(
                script_text,
                reel_id=reel_id,
                card_views=card_views,
                source_url=source_url,
            )
            if index == 0:
                payload = parsed
            else:
                payload = self._merge_reel_payloads(payload, parsed)

        return payload

    def _render_page_html(self, url: str, timeout: int = 60) -> Optional[str]:
        if sync_playwright is None or not self.store.cookie_records:
            return None

        cookies: List[Dict[str, Any]] = []
        for record in self.store.cookie_records:
            domain = clean_text(record.get("domain") or ".facebook.com").lstrip(".")
            cookie: Dict[str, Any] = {
                "name": clean_text(record.get("name")),
                "value": str(record.get("value", "")),
                "domain": domain,
                "path": record.get("path") or "/",
            }
            if record.get("secure") is not None:
                cookie["secure"] = bool(record.get("secure"))
            if record.get("expires") is not None:
                cookie["expires"] = int(record.get("expires"))
            cookies.append(cookie)

        with sync_playwright() as playwright:
            browser = None
            launch_errors: List[str] = []
            for channel in PLAYWRIGHT_BROWSER_CHANNELS:
                try:
                    browser = playwright.chromium.launch(channel=channel, headless=True)
                    break
                except Exception as exc:
                    launch_errors.append(f"{channel}: {exc}")

            if browser is None:
                try:
                    browser = playwright.chromium.launch(headless=True)
                except Exception as exc:
                    launch_errors.append(f"chromium: {exc}")
                    raise RuntimeError("Playwright browser launch failed: " + "; ".join(launch_errors))

            context = browser.new_context(viewport={"width": 1280, "height": 800})
            try:
                context.add_cookies(cookies)
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
                return page.content()
            finally:
                context.close()
                browser.close()

    def _extract_cards(self, html: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        cards: List[Dict[str, Any]] = []
        seen = set()

        for anchor in soup.select('a[href*="/reel/"]'):
            href = anchor.get("href") or ""
            match = re.search(r"/reel/(\d+)", href)
            if not match:
                continue
            reel_id = match.group(1)
            if reel_id in seen:
                continue
            seen.add(reel_id)
            card_views = clean_text(anchor.get_text(" ", strip=True))
            cards.append(
                {
                    "index": len(cards) + 1,
                    "reel_id": reel_id,
                    "url": urljoin(BASE_URL, href),
                    "card_views": card_views,
                    "card_views_value": normalize_compact_count(card_views) or 0,
                }
            )

        return cards

    def _extract_string(self, text: str, patterns: List[str]) -> Optional[str]:
        return first_group(text, patterns)

    def _extract_int(self, text: str, patterns: List[str]) -> Optional[int]:
        value = self._extract_string(text, patterns)
        return safe_int(value)

    def _parse_dash_manifest(self, manifest_xml: str) -> List[Dict[str, Any]]:
        try:
            root = ET.fromstring(manifest_xml)
        except ET.ParseError:
            return []

        renditions: List[Dict[str, Any]] = []
        for element in root.iter():
            if not element.tag.endswith("Representation"):
                continue

            base_url = ""
            for child in list(element):
                if child.tag.endswith("BaseURL") and child.text:
                    base_url = clean_text(child.text)
                    break

            if not base_url:
                continue

            renditions.append(
                {
                    "id": element.attrib.get("id", ""),
                    "bandwidth": safe_int(element.attrib.get("bandwidth"), 0) or 0,
                    "mime_type": element.attrib.get("mimeType", "") or element.attrib.get("mime_type", ""),
                    "codecs": element.attrib.get("codecs", ""),
                    "width": safe_int(element.attrib.get("width"), 0) or 0,
                    "height": safe_int(element.attrib.get("height"), 0) or 0,
                    "quality_class": element.attrib.get("FBQualityClass", ""),
                    "quality_label": element.attrib.get("FBQualityLabel", ""),
                    "base_url": base_url,
                }
            )

        renditions.sort(
            key=lambda item: (
                1 if item["mime_type"].startswith("video/") or item["height"] > 0 else 0,
                item["bandwidth"],
                item["height"],
                item["width"],
            ),
            reverse=True,
        )
        return renditions

    def _choose_best_rendition(self, renditions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not renditions:
            return None
        video_renditions = [item for item in renditions if item["mime_type"].startswith("video/") or item["height"] > 0]
        pool = video_renditions or renditions
        pool.sort(key=lambda item: (item["bandwidth"], item["height"], item["width"]), reverse=True)
        return pool[0] if pool else None

    def _launch_playwright_browser(self, playwright: Any) -> Any:
        browser = None
        launch_errors: List[str] = []

        for channel in PLAYWRIGHT_BROWSER_CHANNELS:
            try:
                browser = playwright.chromium.launch(channel=channel, headless=True)
                break
            except Exception as exc:
                launch_errors.append(f"{channel}: {exc}")

        if browser is None:
            try:
                browser = playwright.chromium.launch(headless=True)
            except Exception as exc:
                launch_errors.append(f"chromium: {exc}")
                raise RuntimeError("Playwright browser launch failed: " + "; ".join(launch_errors))

        return browser

    def _card_views_value(self, card: Dict[str, Any]) -> int:
        value = card.get("card_views_value")
        if isinstance(value, int):
            return value
        return normalize_compact_count(card.get("card_views")) or 0

    def _order_reel_cards(self, cards: List[Dict[str, Any]], order: str) -> List[Dict[str, Any]]:
        order_key = normalize_scan_order(order)
        if order_key == "oldest":
            return list(reversed(cards))
        if order_key == "popular":
            return sorted(
                cards,
                key=lambda card: (self._card_views_value(card), card.get("index", 0) or 0),
                reverse=True,
            )
        return cards

    def _collect_cards_browser(
        self,
        target_url: str,
        max_scrolls: int = 30,
        stable_rounds: int = 2,
        scroll_pause_ms: int = 1200,
    ) -> List[Dict[str, Any]]:
        if sync_playwright is None or not self.store.cookie_records:
            return []

        cookies: List[Dict[str, Any]] = []
        for record in self.store.cookie_records:
            domain = clean_text(record.get("domain") or ".facebook.com").lstrip(".")
            cookie: Dict[str, Any] = {
                "name": clean_text(record.get("name")),
                "value": str(record.get("value", "")),
                "domain": domain,
                "path": record.get("path") or "/",
            }
            if record.get("secure") is not None:
                cookie["secure"] = bool(record.get("secure"))
            if record.get("expires") is not None:
                cookie["expires"] = int(record.get("expires"))
            cookies.append(cookie)

        with sync_playwright() as playwright:
            browser = self._launch_playwright_browser(playwright)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            try:
                context.add_cookies(cookies)
                page = context.new_page()
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1500)

                seen_ids: set[str] = set()
                ordered_cards: List[Dict[str, Any]] = []
                stable_count = 0

                for _ in range(max_scrolls):
                    html = page.content()
                    page_cards = self._extract_cards(html)
                    new_card_found = False
                    for card in page_cards:
                        reel_id = card.get("reel_id", "")
                        if reel_id and reel_id not in seen_ids:
                            seen_ids.add(reel_id)
                            ordered_cards.append(card)
                            new_card_found = True

                    if new_card_found:
                        stable_count = 0
                    else:
                        stable_count += 1

                    if stable_count >= stable_rounds:
                        break

                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(scroll_pause_ms)

                html = page.content()
                for card in self._extract_cards(html):
                    reel_id = card.get("reel_id", "")
                    if reel_id and reel_id not in seen_ids:
                        seen_ids.add(reel_id)
                        ordered_cards.append(card)

                return ordered_cards
            finally:
                context.close()
                browser.close()

    def _collect_cards(self, target_url: str, use_browser_scroll: bool = False) -> List[Dict[str, Any]]:
        if use_browser_scroll and sync_playwright is not None and self.store.cookie_records:
            cards = self._collect_cards_browser(target_url)
            if cards:
                return cards

        response = self._request(target_url)
        if self._looks_like_login_form(response.text, response.url):
            raise RuntimeError("session looks logged out; import cookies first")

        return self._extract_cards(response.text)

    def _parse_reel_blob(self, text: str, reel_id: str, card_views: str = "", source_url: str = "") -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "index": None,
            "reel_id": reel_id,
            "url": source_url or f"{BASE_URL}/reel/{reel_id}",
            "card_views": card_views,
            "title": "",
            "description": "",
            "likes": None,
            "likes_raw": "",
            "comments": None,
            "comments_raw": "",
            "shares": None,
            "shares_raw": "",
            "duration_seconds": None,
            "thumbnail_url": "",
            "best_cdn_url": "",
            "best_cdn_quality": "",
            "best_cdn_bandwidth": 0,
            "manifest_count": 0,
            "renditions": [],
            "status": "ok",
            "error": "",
        }

        message_patterns = [
            r'"message":\{"text":"((?:\\.|[^"\\])*)"',
            r'"translated_message_for_viewer":\{"text":"((?:\\.|[^"\\])*)"',
        ]
        likes_patterns = [
            r'"likers":\{"count":(\d+)',
            r'"unified_reactors":\{"count":(\d+)',
            r'"reaction_count":(\d+)',
            r'"aggregated_reaction_count":(\d+)',
        ]
        comments_patterns = [
            r'"total_comment_count":(\d+)',
            r'"aggregated_comment_count":(\d+)',
            r'"comment_count":(\d+)',
        ]
        shares_patterns = [
            r'"share_count_reduced":"((?:\\.|[^"\\])*)"',
            r'"share_count":"((?:\\.|[^"\\])*)"',
        ]
        thumb_patterns = [
            r'"first_frame_thumbnail":"((?:\\.|[^"\\])*)"',
        ]
        manifest_patterns = [
            r'(?s)"dash_manifest_xml_string":"(.*?)",',
            r'(?s)"dash_manifest_xml":"(.*?)",',
            r'(?s)manifest_xml":"(.*?)",',
        ]
        duration_ms_patterns = [
            r'"playable_duration_in_ms":(\d+)',
        ]
        duration_s_patterns = [
            r'"length_in_second":([0-9.]+)',
            r'"length_in_seconds":([0-9.]+)',
        ]
        direct_video_patterns = [
            r'"playable_url_quality_hd":"((?:\\.|[^"\\])*)"',
            r'"playable_url":"((?:\\.|[^"\\])*)"',
            r'"hd_src":"((?:\\.|[^"\\])*)"',
            r'"sd_src":"((?:\\.|[^"\\])*)"',
        ]

        message_raw = self._extract_string(text, message_patterns)
        if message_raw:
            message = decode_js_escaped(message_raw)
            payload["description"] = message
            payload["title"] = message.split("\n\n", 1)[0].strip()

        likes_raw = self._extract_string(text, likes_patterns)
        if likes_raw is not None:
            payload["likes_raw"] = likes_raw
            payload["likes"] = safe_int(likes_raw)

        comments_raw = self._extract_string(text, comments_patterns)
        if comments_raw is not None:
            payload["comments_raw"] = comments_raw
            payload["comments"] = safe_int(comments_raw)

        shares_raw = self._extract_string(text, shares_patterns)
        if shares_raw:
            shares_text = decode_js_escaped(shares_raw)
            payload["shares_raw"] = shares_text
            payload["shares"] = normalize_compact_count(shares_text)

        thumb_raw = self._extract_string(text, thumb_patterns)
        if thumb_raw:
            payload["thumbnail_url"] = decode_js_escaped(thumb_raw)

        duration_ms_raw = self._extract_string(text, duration_ms_patterns)
        if duration_ms_raw:
            payload["duration_seconds"] = round((safe_int(duration_ms_raw, 0) or 0) / 1000.0, 3)
        else:
            duration_s_raw = self._extract_string(text, duration_s_patterns)
            if duration_s_raw:
                payload["duration_seconds"] = safe_float(duration_s_raw)

        manifest_raw = self._extract_string(text, manifest_patterns)
        if manifest_raw:
            manifest_xml = decode_js_escaped(manifest_raw)
            renditions = self._parse_dash_manifest(manifest_xml)
            payload["renditions"] = renditions
            payload["manifest_count"] = len(renditions)
            best = self._choose_best_rendition(renditions)
            if best:
                payload["best_cdn_url"] = best["base_url"]
                payload["best_cdn_quality"] = (
                    best.get("quality_label")
                    or best.get("quality_class")
                    or f"{best.get('width')}x{best.get('height')}"
                )
                payload["best_cdn_bandwidth"] = best.get("bandwidth", 0)

        if not payload["best_cdn_url"]:
            direct_url_raw = self._extract_string(text, direct_video_patterns)
            if direct_url_raw:
                payload["best_cdn_url"] = decode_js_escaped(direct_url_raw)
                payload["best_cdn_quality"] = "direct"

        if not payload["title"] and payload["description"]:
            payload["title"] = payload["description"].split("\n\n", 1)[0].strip()

        if not payload["title"]:
            payload["status"] = "partial"

        return payload

    def fetch_reel_summary(self, card: Dict[str, Any]) -> Dict[str, Any]:
        response = self._request(card["url"])
        if self._looks_like_login_form(response.text, response.url):
            return {
                "index": card["index"],
                "reel_id": card["reel_id"],
                "url": response.url,
                "card_views": card.get("card_views", ""),
                "status": "login_required",
                "error": "session looks logged out",
            }

        summary = self._parse_reel_payload_from_html(
            response.text,
            reel_id=card["reel_id"],
            card_views=card.get("card_views", ""),
            source_url=response.url,
        )

        if not summary.get("best_cdn_url"):
            try:
                detail = self.fetch_reel_detail(card["reel_id"])
                summary = self._merge_reel_payloads(summary, detail)
            except Exception:
                pass

        if not summary.get("best_cdn_url"):
            try:
                rendered_html = self._render_page_html(card["url"])
                if rendered_html:
                    rendered_summary = self._parse_reel_payload_from_html(
                        rendered_html,
                        reel_id=card["reel_id"],
                        card_views=card.get("card_views", ""),
                        source_url=response.url,
                    )
                    summary = self._merge_reel_payloads(summary, rendered_summary)
            except Exception:
                pass

        summary["index"] = card["index"]
        summary["url"] = response.url or card["url"]
        summary["card_views"] = card.get("card_views", "")
        summary["status"] = summary.get("status") or "ok"
        return summary

    def fetch_reel_detail(self, reel_id: str, source_url: Optional[str] = None) -> Dict[str, Any]:
        url = source_url or f"{BASE_URL}/reel/{reel_id}"
        response = self._request(url)
        if self._looks_like_login_form(response.text, response.url):
            raise RuntimeError("session looks logged out; import cookies first")

        detail = self._parse_reel_payload_from_html(
            response.text,
            reel_id=reel_id,
            source_url=response.url,
        )

        if not detail.get("best_cdn_url"):
            try:
                rendered_html = self._render_page_html(url)
                if rendered_html:
                    rendered_detail = self._parse_reel_payload_from_html(
                        rendered_html,
                        reel_id=reel_id,
                        source_url=response.url,
                    )
                    detail = self._merge_reel_payloads(detail, rendered_detail)
            except Exception:
                pass

        detail["url"] = response.url or url
        detail["status"] = "ok" if detail.get("best_cdn_url") else detail.get("status", "partial")
        return detail

    def scan_reels_page(
        self,
        target_url: Optional[str] = None,
        max_reels: Optional[int] = None,
        order: str = "newest",
        use_browser_scroll: bool = False,
    ) -> List[Dict[str, Any]]:
        target = target_url or self.target
        print(f"[*] Fetching reels page: {target}")
        cards = self._collect_cards(target, use_browser_scroll=use_browser_scroll)
        if not cards:
            raise RuntimeError(
                "No reel cards found on the page. Import a valid session cookie or try a different target."
            )

        total_cards = len(cards)
        ordered_cards = self._order_reel_cards(cards, order)

        if max_reels is not None and max_reels > 0:
            ordered_cards = ordered_cards[:max_reels]

        for selected_index, card in enumerate(ordered_cards, 1):
            card["scan_index"] = selected_index

        print(f"[*] Total reel cards detected: {total_cards}")
        print(f"[*] Scraping {len(ordered_cards)} reel cards using order: {normalize_scan_order(order)}")
        results: List[Dict[str, Any]] = []
        max_workers = min(self.workers, len(ordered_cards))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(self.fetch_reel_summary, card): card for card in ordered_cards}
            for done_count, future in enumerate(as_completed(future_map), 1):
                card = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "index": card["index"],
                        "scan_index": card.get("scan_index", card["index"]),
                        "reel_id": card["reel_id"],
                        "url": card["url"],
                        "card_views": card.get("card_views", ""),
                        "status": "error",
                        "error": str(exc),
                    }
                result["scan_index"] = card.get("scan_index", card["index"])
                results.append(result)
                print(f"    [{done_count}/{len(ordered_cards)}] {card['reel_id']} done")

        results.sort(key=lambda item: item.get("scan_index", 0) or 0)
        self.last_scan = results
        self._save_json(results, f"scan_{now_stamp()}.json")
        self.print_scan(results)
        return results

    def _save_json(self, data: Any, filename: str) -> Path:
        path = OUTPUT_DIR / filename
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def save_detail(self, detail: Dict[str, Any]) -> Path:
        reel_id = detail.get("reel_id", "reel")
        return self._save_json(detail, f"detail_{safe_filename(reel_id)}_{now_stamp()}.json")

    def print_scan(self, results: List[Dict[str, Any]]) -> None:
        print("\n" + "=" * 88)
        print("LAYER 1 - REEL SUMMARY")
        print("=" * 88)
        for item in results:
            idx = item.get("scan_index", item.get("index", 0)) or 0
            print(f"[{idx:02d}] {item.get('reel_id', '-')}")
            print(f"     URL       : {item.get('url', '-')}")
            print(f"     Views     : {format_metric(None, item.get('card_views', ''))}")
            print(f"     Likes     : {format_metric(item.get('likes'), item.get('likes_raw'))}")
            print(f"     Comments  : {format_metric(item.get('comments'), item.get('comments_raw'))}")
            print(f"     Shares    : {format_metric(item.get('shares'), item.get('shares_raw'))}")
            if item.get("best_cdn_quality"):
                print(f"     CDN       : {item.get('best_cdn_quality')}")
            if item.get("best_cdn_url"):
                print(f"     CDN URL   : {item.get('best_cdn_url')}")
            if item.get("manifest_count"):
                print(f"     Variants  : {item.get('manifest_count')} renditions")
            print(f"     Title     : {truncate(item.get('title', ''), 90)}")
            print(f"     Desc      : {truncate(item.get('description', ''), 140)}")
            if item.get("status") not in (None, "ok"):
                print(f"     Status    : {item.get('status')}")
            if item.get("error"):
                print(f"     Error     : {item.get('error')}")
            print()

    def print_detail(self, detail: Dict[str, Any]) -> None:
        print("\n" + "=" * 88)
        print("LAYER 2 - REEL DETAIL")
        print("=" * 88)
        print(f"Reel ID   : {detail.get('reel_id', '-')}")
        print(f"URL       : {detail.get('url', '-')}")
        print(f"Title     : {detail.get('title', '-')}")
        print(f"Likes     : {format_metric(detail.get('likes'), detail.get('likes_raw'))}")
        print(f"Comments  : {format_metric(detail.get('comments'), detail.get('comments_raw'))}")
        print(f"Shares    : {format_metric(detail.get('shares'), detail.get('shares_raw'))}")
        if detail.get("card_views"):
            print(f"Views     : {detail.get('card_views')}")
        if detail.get("duration_seconds") is not None:
            print(f"Duration  : {detail.get('duration_seconds')} seconds")
        if detail.get("best_cdn_quality"):
            print(f"Best CDN  : {detail.get('best_cdn_quality')}")
        if detail.get("best_cdn_url"):
            print(f"Best URL  : {detail.get('best_cdn_url')}")
        if detail.get("description"):
            print("\nDescription:")
            print(textwrap.indent(detail["description"], "    "))

        renditions = detail.get("renditions", []) or []
        if renditions:
            print("\nRenditions:")
            for idx, rendition in enumerate(renditions, 1):
                label = (
                    rendition.get("quality_label")
                    or rendition.get("quality_class")
                    or rendition.get("mime_type")
                    or "-"
                )
                size = "-"
                if rendition.get("width") and rendition.get("height"):
                    size = f"{rendition['width']}x{rendition['height']}"
                bandwidth = rendition.get("bandwidth", 0)
                print(f"  [{idx:02d}] {label} | {size} | {bandwidth:,}")
                print(f"       {rendition.get('base_url', '-')}")
        else:
            print("\nRenditions: none found")

    def choose_from_results(self, results: List[Dict[str, Any]]) -> Optional[str]:
        if not results:
            return None

        print("\nPilih nomor reel atau reel id untuk detail CDN")
        choice = input("Masukkan pilihan (Enter untuk batal): ").strip()
        if not choice:
            return None

        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(results):
                return results[index - 1].get("reel_id")

        for item in results:
            if item.get("reel_id") == choice:
                return choice

        print("[!] Pilihan tidak valid")
        return None

    def resolve_account_identity(self) -> Dict[str, str]:
        identity: Dict[str, str] = {
            "name": clean_text(self.store.meta.get("account_name", "")),
            "id": clean_text(self.store.meta.get("account_id", "")) or self.store.get_cookie_value("c_user"),
            "url": clean_text(self.store.meta.get("account_url", "")),
        }

        if identity["name"]:
            return identity

        response = self._request(f"{BASE_URL}/me")
        if self._looks_like_login_form(response.text, response.url):
            return identity

        account_name = extract_facebook_profile_name(response.text)
        if account_name:
            identity["name"] = account_name
            identity["url"] = response.url or f"{BASE_URL}/me"

        return identity


def show_session_status(store: SessionStore, scraper: ReelsScraper) -> None:
    print("\n" + "=" * 88)
    print("SESSION STATUS")
    print("=" * 88)

    if not store.cookie_records:
        print(store.describe())
        print("\nNo session cookies loaded yet.")
        return

    try:
        response = scraper._request(scraper.target)
        if scraper._looks_like_login_form(response.text, response.url):
            print("\nSession test : looks logged out")
        else:
            cards = scraper._extract_cards(response.text)
            print(f"\nSession test : usable, {len(cards)} reel cards detected")

        identity = scraper.resolve_account_identity()
        if identity.get("name") or identity.get("id"):
            if identity.get("name") and store.meta.get("account_name") != identity["name"]:
                store.meta["account_name"] = identity["name"]
                store.meta["account_id"] = identity.get("id") or store.meta.get("account_id") or store.get_cookie_value("c_user")
                if identity.get("url"):
                    store.meta["account_url"] = identity["url"]
                store.save()

        print(store.describe())
    except Exception as exc:
        print(f"\nSession test : failed ({exc})")


def login_menu(store: SessionStore, scraper: ReelsScraper) -> None:
    while True:
        print("\n" + "-" * 88)
        print("LOGIN / SESSION MENU")
        print("-" * 88)
        print("1. Login via browser and auto-save session")
        print("2. Paste cookie string")
        print("3. Load cookie JSON / storageState file")
        print("4. Load Netscape cookie file")
        print("5. Clear saved session")
        print("6. Back")
        choice = input("> ").strip()

        try:
            if choice == "1":
                login_via_browser(store, scraper)
                show_session_status(store, scraper)
            elif choice == "2":
                print("Paste the cookie string here. Urutan bebas; duplikat key akan dipakai yang terakhir.")
                cookie_string = getpass("Cookie string: ")
                store.import_cookie_string(cookie_string)
                print(f"[+] Session saved to {store.path}")
                show_session_status(store, scraper)
            elif choice == "3":
                file_path = input("Path to JSON file: ").strip().strip('"')
                store.import_cookie_file(file_path)
                print(f"[+] Session saved to {store.path}")
                show_session_status(store, scraper)
            elif choice == "4":
                file_path = input("Path to Netscape cookie file: ").strip().strip('"')
                store.import_cookie_file(file_path)
                print(f"[+] Session saved to {store.path}")
                show_session_status(store, scraper)
            elif choice == "5":
                store.clear()
                print("[+] Session cleared")
            elif choice == "6":
                return
            else:
                print("[!] Unknown choice")
        except Exception as exc:
            print(f"[!] Login/session action failed: {exc}")


def prompt_scan_options(scraper: ReelsScraper) -> Dict[str, Any]:
    print("\n" + "-" * 88)
    print("SCAN OPTIONS")
    print("-" * 88)
    target = input(f"Target reels page URL [{scraper.target}]: ").strip() or scraper.target
    print("1. Terbaru / dari atas")
    print("2. Dari bawah / paling lama")
    print("3. Paling populer (views terbesar)")
    order = normalize_scan_order(input("Urutan [1]: ").strip() or "1")
    limit_text = input("Mau scrape berapa reel? (Enter = semua): ").strip()
    max_reels = safe_int(limit_text) if limit_text else None
    if max_reels is not None and max_reels <= 0:
        max_reels = None

    return {
        "target": target,
        "order": order,
        "max_reels": max_reels,
    }


def interactive_menu(scraper: ReelsScraper, store: SessionStore) -> None:
    while True:
        print("\n" + "=" * 88)
        print("FACEBOOK REELS CLI")
        print("=" * 88)
        print("1. Login / import session")
        print("2. Scan reels page in parallel")
        print("3. Inspect reel by ID")
        print("4. Session status")
        print("5. Clear session")
        print("0. Exit")
        choice = input("> ").strip()

        try:
            if choice == "1":
                login_menu(store, scraper)
            elif choice == "2":
                scan_options = prompt_scan_options(scraper)
                print("[*] Menu scan akan menghitung total reels dulu lalu scrape sesuai pilihan urutan dan jumlah.")
                results = scraper.scan_reels_page(
                    target_url=scan_options["target"],
                    max_reels=scan_options["max_reels"],
                    order=scan_options["order"],
                    use_browser_scroll=True,
                )
                if results:
                    reel_id = scraper.choose_from_results(results)
                    if reel_id:
                        detail = scraper.fetch_reel_detail(reel_id)
                        scraper.save_detail(detail)
                        scraper.print_detail(detail)
            elif choice == "3":
                reel_id = input("Reel ID: ").strip()
                if reel_id:
                    detail = scraper.fetch_reel_detail(reel_id)
                    scraper.save_detail(detail)
                    scraper.print_detail(detail)
            elif choice == "4":
                show_session_status(store, scraper)
            elif choice == "5":
                confirm = input("Clear saved session file? [y/N]: ").strip().lower()
                if confirm == "y":
                    store.clear()
                    print("[+] Session cleared")
            elif choice == "0":
                return
            else:
                print("[!] Unknown choice")
        except KeyboardInterrupt:
            print("\n[!] Interrupted")
        except Exception as exc:
            print(f"[!] Error: {exc}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Facebook Reels 2-layer scraper")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="Reels page URL")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Parallel worker count")
    parser.add_argument("--login", action="store_true", help="Open browser login and auto-save session")
    parser.add_argument("--login-timeout", type=int, default=DEFAULT_LOGIN_TIMEOUT, help="Seconds to wait for browser login")
    parser.add_argument("--login-poll", type=int, default=DEFAULT_LOGIN_POLL, help="Seconds between browser cookie checks")
    parser.add_argument("--scan", action="store_true", help="Run layer 1 scan")
    parser.add_argument("--reel-id", help="Fetch layer 2 detail for a reel ID")
    parser.add_argument("--import-cookie-string", help="Import a raw cookie string; order does not matter")
    parser.add_argument("--import-cookie-file", help="Import cookies from a JSON or Netscape file")
    parser.add_argument("--show-session", action="store_true", help="Print session status and exit")
    parser.add_argument("--clear-session", action="store_true", help="Delete the saved session and exit")
    parser.add_argument("--no-menu", action="store_true", help="Do not open the interactive menu")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    ensure_dir(APP_DIR)
    ensure_dir(OUTPUT_DIR)

    store = SessionStore()
    scraper = ReelsScraper(store, target=args.target, workers=args.workers)

    try:
        requested_action = any(
            [
                args.clear_session,
                bool(args.import_cookie_string),
                bool(args.import_cookie_file),
                args.login,
                args.show_session,
                args.scan,
                bool(args.reel_id),
            ]
        )

        if args.clear_session:
            store.clear()
            print("[+] Session cleared")
            return 0

        if args.import_cookie_string:
            store.import_cookie_string(args.import_cookie_string)
            print(f"[+] Session saved to {store.path}")

        if args.import_cookie_file:
            store.import_cookie_file(args.import_cookie_file)
            print(f"[+] Session saved to {store.path}")

        if args.login:
            login_via_browser(
                store,
                scraper,
                target_url=args.target,
                timeout=args.login_timeout,
                poll_interval=args.login_poll,
            )

        if args.show_session:
            show_session_status(store, scraper)
            return 0

        if args.scan:
            results = scraper.scan_reels_page(args.target)
            if args.reel_id:
                detail = scraper.fetch_reel_detail(args.reel_id)
                scraper.save_detail(detail)
                scraper.print_detail(detail)
                return 0
            if args.no_menu:
                return 0
            reel_id = scraper.choose_from_results(results)
            if reel_id:
                detail = scraper.fetch_reel_detail(reel_id)
                scraper.save_detail(detail)
                scraper.print_detail(detail)
            return 0

        if args.reel_id:
            detail = scraper.fetch_reel_detail(args.reel_id)
            scraper.save_detail(detail)
            scraper.print_detail(detail)
            return 0

        if args.no_menu:
            if not requested_action:
                parser.print_help()
            return 0

        interactive_menu(scraper, store)
        return 0
    except KeyboardInterrupt:
        print("\n[!] Interrupted")
        return 130
    except Exception as exc:
        print(f"[!] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
