from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from CLI_Mode.facebook_reels_cli import DEFAULT_TARGET as CLI_DEFAULT_TARGET
from CLI_Mode.facebook_reels_cli import DEFAULT_WORKERS as CLI_DEFAULT_WORKERS


DEFAULT_BANNER_URL: Final[str] = ""
DEFAULT_SESSION_FILE = Path("CLI_Mode") / "bot_session.json"
DEFAULT_OUTPUT_DIR = Path("CLI_Mode") / "output"
DEFAULT_SESSION_DIR = Path("storage") / "sessions"
DEFAULT_TEMP_DIR = Path("storage") / "temp"


def _dotenv_values(path: Path = Path(".env")) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _is_placeholder_token(name: str, value: str) -> bool:
    if "TOKEN" not in name.upper():
        return False
    lowered = value.strip().lower()
    return lowered in {"123:dummy", "dummy", "test:dummy"} or "dummy" in lowered


def _first_env(*names: str, default: str = "") -> str:
    dotenv = _dotenv_values()
    placeholder = ""
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            cleaned = value.strip()
            if _is_placeholder_token(name, cleaned):
                placeholder = cleaned
                continue
            return cleaned
    for name in names:
        value = dotenv.get(name)
        if value is not None and value.strip():
            cleaned = value.strip()
            if _is_placeholder_token(name, cleaned):
                placeholder = cleaned
                continue
            return cleaned
    if placeholder:
        return placeholder
    return default


def _first_env_int(*names: str, default: int) -> int:
    dotenv = _dotenv_values()
    for name in names:
        raw = os.environ.get(name) or dotenv.get(name)
        if raw is None or not raw.strip():
            continue
        try:
            return int(raw)
        except ValueError:
            continue
    return default


def _first_env_path(*names: str, default: Path) -> Path:
    raw = _first_env(*names, default="")
    return Path(raw) if raw else default


@dataclass(frozen=True, slots=True)
class BotConfig:
    bot_token: str
    admin_user_id: int
    banner_url: str
    default_workers: int
    default_target: str
    session_file: Path
    session_dir: Path
    output_dir: Path
    temp_dir: Path


def load_config() -> BotConfig:
    bot_token = _first_env("BOT_TOKEN", "TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set")

    session_file = _first_env_path("SESSION_FILE", "BOT_SESSION_FILE", "FB_REELS_SESSION_FILE", default=DEFAULT_SESSION_FILE)
    session_dir = _first_env_path("SESSION_DIR", "BOT_SESSION_DIR", "TELEGRAM_SESSION_DIR", default=DEFAULT_SESSION_DIR)
    output_dir = _first_env_path("OUTPUT_DIR", "BOT_OUTPUT_DIR", "FB_REELS_OUTPUT_DIR", default=DEFAULT_OUTPUT_DIR)
    temp_dir = _first_env_path("TEMP_DIR", "BOT_TEMP_DIR", "TELEGRAM_TEMP_DIR", default=DEFAULT_TEMP_DIR)
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    return BotConfig(
        bot_token=bot_token,
        admin_user_id=_first_env_int("ADMIN_USER_ID", "TELEGRAM_ADMIN_USER_ID", default=0),
        banner_url=_first_env("BANNER_URL", "BOT_BANNER_URL", "TELEGRAM_BANNER_URL", default=DEFAULT_BANNER_URL),
        default_workers=_first_env_int("DEFAULT_WORKERS", "BOT_DEFAULT_WORKERS", "TELEGRAM_DEFAULT_WORKERS", default=CLI_DEFAULT_WORKERS),
        default_target=_first_env("DEFAULT_TARGET", "BOT_DEFAULT_TARGET", "TELEGRAM_DEFAULT_TARGET", default=CLI_DEFAULT_TARGET),
        session_file=session_file,
        session_dir=session_dir,
        output_dir=output_dir,
        temp_dir=temp_dir,
    )
