from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def to_json_text(payload: Any) -> str:
    def default(value: Any) -> Any:
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, Path):
            return str(value)
        return str(value)

    return json.dumps(payload, ensure_ascii=False, indent=2, default=default)
