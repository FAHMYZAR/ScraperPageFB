from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(slots=True)
class SessionStatus:
    available: bool
    valid: Optional[bool]
    source: str
    account_name: str = ""
    account_id: str = ""
    cookie_count: int = 0
    reel_count: int = 0
    last_checked_at: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "valid": self.valid,
            "source": self.source,
            "account_name": self.account_name,
            "account_id": self.account_id,
            "cookie_count": self.cookie_count,
            "reel_count": self.reel_count,
            "last_checked_at": self.last_checked_at,
            "error": self.error,
        }
