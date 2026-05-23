from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from CLI_Mode.facebook_reels_cli import normalize_compact_count, safe_int


@dataclass(slots=True)
class Reel:
    id: str
    title: str
    description: str = ""
    url: str = ""
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    card_views_text: str = ""
    best_cdn_url: str = ""
    best_cdn_quality: str = ""
    manifest_count: int = 0
    scan_index: int = 0
    source_url: str = ""
    raw: Dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_summary(cls, data: Dict[str, Any]) -> "Reel":
        card_views = str(data.get("card_views", "") or "")
        views_value = safe_int(data.get("card_views_value"), 0) or normalize_compact_count(card_views) or 0
        return cls(
            id=str(data.get("reel_id") or data.get("id") or ""),
            title=str(data.get("title", "") or ""),
            description=str(data.get("description", "") or ""),
            url=str(data.get("url", "") or ""),
            views=views_value,
            likes=safe_int(data.get("likes"), 0) or 0,
            comments=safe_int(data.get("comments"), 0) or 0,
            shares=safe_int(data.get("shares"), 0) or 0,
            card_views_text=card_views,
            best_cdn_url=str(data.get("best_cdn_url", "") or ""),
            best_cdn_quality=str(data.get("best_cdn_quality", "") or ""),
            manifest_count=safe_int(data.get("manifest_count"), 0) or 0,
            scan_index=safe_int(data.get("scan_index"), 0) or safe_int(data.get("index"), 0) or 0,
            source_url=str(data.get("source_url", "") or data.get("url", "") or ""),
            raw=dict(data),
        )

    @property
    def reel_id(self) -> str:
        return self.id

    def popularity_score(self) -> int:
        return (self.views * 10) + (self.likes * 5) + (self.comments * 3) + (self.shares * 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reel_id": self.id,
            "title": self.title,
            "description": self.description,
            "url": self.url,
            "views": self.views,
            "likes": self.likes,
            "comments": self.comments,
            "shares": self.shares,
            "card_views": self.card_views_text,
            "best_cdn_url": self.best_cdn_url,
            "best_cdn_quality": self.best_cdn_quality,
            "manifest_count": self.manifest_count,
            "scan_index": self.scan_index,
            "source_url": self.source_url,
        }
