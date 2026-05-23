from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(slots=True)
class PageInfo:
    name: str
    title: str
    url: str = ""
    total_items: int = 0
    total_reels: int = 0
    detected_cards: int = 0
    source: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "url": self.url,
            "total_items": self.total_items,
            "total_reels": self.total_reels,
            "detected_cards": self.detected_cards,
            "source": self.source,
            "description": self.description,
        }
