from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

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

    def import_cookie_string(self, raw_cookie: str) -> None:
        self.store.import_cookie_string(raw_cookie)

    def import_cookie_file(self, file_path: str) -> None:
        self.store.import_cookie_file(file_path)

    def clear(self) -> None:
        self.store.clear()

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
