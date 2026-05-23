from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(slots=True)
class CdnVariant:
    url: str
    quality: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    bitrate: Optional[int] = None
    mime_type: str = "video/mp4"
    has_audio: bool = False
    is_audio_only: bool = False

    @classmethod
    def from_rendition(cls, data: Dict[str, Any]) -> "CdnVariant":
        mime_type = str(data.get("mime_type") or "")
        width = int(data.get("width") or 0) or None
        height = int(data.get("height") or 0) or None
        is_audio = mime_type.startswith("audio/") or (not width and not height)
        quality = str(data.get("quality_label") or data.get("quality_class") or "").strip() or None
        if not quality and height:
            quality = f"{height}p"
        return cls(
            url=str(data.get("base_url") or data.get("url") or ""),
            quality=quality,
            width=width,
            height=height,
            bitrate=int(data.get("bandwidth") or data.get("bitrate") or 0) or None,
            mime_type=mime_type or ("audio/mp4" if is_audio else "video/mp4"),
            has_audio=bool(data.get("has_audio", False)),
            is_audio_only=bool(data.get("is_audio_only", is_audio)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "quality": self.quality,
            "width": self.width,
            "height": self.height,
            "bitrate": self.bitrate,
            "mime_type": self.mime_type,
            "has_audio": self.has_audio,
            "is_audio_only": self.is_audio_only,
        }
