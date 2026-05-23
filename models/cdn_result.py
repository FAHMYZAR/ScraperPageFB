from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class CdnResult:
    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    merged_audio_video_url: Optional[str] = None
    quality: Optional[str] = None
    title: str = ""
    description: str = ""
    reel_id: str = ""
    source_url: str = ""
    thumbnail_url: str = ""
    best_bandwidth: int = 0
    renditions: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "ok"

    @property
    def best_url(self) -> Optional[str]:
        return self.merged_audio_video_url or self.video_url

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_url": self.video_url,
            "audio_url": self.audio_url,
            "merged_audio_video_url": self.merged_audio_video_url,
            "quality": self.quality,
            "title": self.title,
            "description": self.description,
            "reel_id": self.reel_id,
            "source_url": self.source_url,
            "thumbnail_url": self.thumbnail_url,
            "best_bandwidth": self.best_bandwidth,
            "renditions": self.renditions,
            "status": self.status,
        }
