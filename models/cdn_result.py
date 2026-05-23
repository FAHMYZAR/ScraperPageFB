from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from models.cdn_variant import CdnVariant


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
    video_variants: List[CdnVariant] = field(default_factory=list)
    audio_variants: List[CdnVariant] = field(default_factory=list)
    best_video: Optional[CdnVariant] = None
    best_audio: Optional[CdnVariant] = None
    final_file_path: Optional[str] = None
    status: str = "ok"

    @property
    def best_url(self) -> Optional[str]:
        return self.merged_audio_video_url or self.video_url or (self.best_video.url if self.best_video else None)

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
            "video_variants": [item.to_dict() for item in self.video_variants],
            "audio_variants": [item.to_dict() for item in self.audio_variants],
            "best_video": self.best_video.to_dict() if self.best_video else None,
            "best_audio": self.best_audio.to_dict() if self.best_audio else None,
            "final_file_path": self.final_file_path,
            "status": self.status,
        }
