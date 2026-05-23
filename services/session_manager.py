from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import CLI_Mode.facebook_reels_cli as fb_cli
from CLI_Mode.facebook_reels_cli import SessionStore
from models import SessionStatus


@dataclass(slots=True)
class SessionManager:
    session_file: Path
    store: SessionStore = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.store = SessionStore(path=self.session_file)

    @property
    def available(self) -> bool:
        return bool(self.store.cookie_records)

    @property
    def account_name(self) -> str:
        return str(self.store.meta.get("account_name", "") or "")

    @property
    def account_id(self) -> str:
        return str(self.store.meta.get("account_id", "") or self.store.get_cookie_value("c_user") or "")

    @property
    def source(self) -> str:
        return str(self.store.meta.get("source", "unknown") or "unknown")

    @property
    def storage_id(self) -> str:
        return self.session_file.stem

    def import_cookie_string(self, raw_cookie: str) -> None:
        self.store.import_cookie_string(raw_cookie)

    def import_cookie_file(self, file_path: str) -> None:
        self.store.import_cookie_file(file_path)

    def import_from_manager(self, source: "SessionManager", source_name: str = "imported_session") -> None:
        if not source.store.cookie_records:
            raise RuntimeError("Session sumber kosong.")
        meta = dict(source.store.meta)
        meta["source"] = meta.get("source") or source_name
        meta["imported_from"] = str(source.session_file)
        self.store.import_cookie_records(list(source.store.cookie_records), str(meta["source"]), meta)

    def import_browser_cookies(self, target_url: str) -> None:
        browser_name, records = fb_cli.load_browser_cookie_records("facebook.com")
        if not fb_cli.has_browser_login_cookies(records):
            raise RuntimeError("Cookie browser belum berisi session login Facebook.")
        self.store.import_cookie_records(records, f"browser_login:{browser_name}", {"target": target_url})

    def clear(self) -> None:
        self.store.clear()

    clear_session = clear

    def build_requests_session(self):
        return self.store.build_requests_session()

    def status_snapshot(
        self,
        valid: Optional[bool] = None,
        reel_count: int = 0,
        error: str = "",
        last_checked_at: str = "",
    ) -> SessionStatus:
        return SessionStatus(
            available=self.available,
            valid=valid,
            source=self.source,
            account_name=self.account_name,
            account_id=self.account_id,
            cookie_count=len(self.store.cookie_records),
            reel_count=reel_count,
            last_checked_at=last_checked_at,
            error=error,
        )
