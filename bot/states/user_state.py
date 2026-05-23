from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from models import CdnResult, PageInfo, Reel


@dataclass(slots=True)
class UserState:
    awaiting: Optional[str] = None
    control_chat_id: Optional[int] = None
    control_message_id: Optional[int] = None
    control_message_kind: str = "text"
    home_message_id: Optional[int] = None
    scan_target: str = ""
    scan_order: str = "newest"
    scan_limit: Optional[int] = None
    scan_page: int = 1
    scan_page_size: int = 3
    scan_mode: str = "newest"
    selected_indices: Set[int] = field(default_factory=set)
    page_info: Optional[PageInfo] = None
    reels: List[Reel] = field(default_factory=list)
    popular_reels: List[Reel] = field(default_factory=list)
    last_detail: Optional[CdnResult] = None
    download_url: str = ""
    last_error: str = ""
    last_checked_at: str = ""

    def reset_scan(self) -> None:
        self.scan_target = ""
        self.scan_order = "newest"
        self.scan_limit = None
        self.scan_page = 1
        self.scan_mode = "newest"
        self.selected_indices.clear()
        self.page_info = None
        self.reels = []
        self.popular_reels = []
        self.last_detail = None

    def reset_download(self) -> None:
        self.download_url = ""
        self.last_detail = None

    def set_control_message(self, chat_id: int, message_id: int) -> None:
        self.control_chat_id = chat_id
        self.control_message_id = message_id

    def toggle_selected(self, index: int) -> None:
        if index in self.selected_indices:
            self.selected_indices.remove(index)
        else:
            self.selected_indices.add(index)

    def clear(self) -> None:
        self.awaiting = None
        self.control_chat_id = None
        self.control_message_id = None
        self.control_message_kind = "text"
        self.home_message_id = None
        self.reset_scan()
        self.reset_download()
        self.last_error = ""
        self.last_checked_at = ""
