from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class UserFlowState:
    awaiting: Optional[str] = None
    scan_draft: Dict[str, Any] = field(default_factory=dict)
    last_scan_results: List[Dict[str, Any]] = field(default_factory=list)
    last_detail: Dict[str, Any] = field(default_factory=dict)
    media_options: List[Dict[str, Any]] = field(default_factory=list)
    control_chat_id: Optional[int] = None
    control_message_id: Optional[int] = None
    control_message_kind: str = "text"
    last_scan_target: str = ""

    def reset_scan_draft(self) -> None:
        self.scan_draft = {}

    def set_control_message(self, chat_id: int, message_id: int) -> None:
        self.control_chat_id = chat_id
        self.control_message_id = message_id
