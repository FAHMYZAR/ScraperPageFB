from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from facebook_reels_cli import DEFAULT_TARGET, DEFAULT_WORKERS


DEFAULT_BANNER_URL = "https://files.catbox.moe/jf8h8x.png"


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_user_id: int
    banner_url: str
    default_workers: int
    default_target: str
    session_file: Path
    output_dir: Path


def _load_dotenv_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]

        os.environ.setdefault(key, value)


def _int_from_env(raw: str, default_value: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default_value
    return value if value > 0 else default_value


def load_settings() -> Settings:
    _load_dotenv_file(Path(".env"))

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    admin_raw = os.getenv("TELEGRAM_ADMIN_USER_ID", "").strip()

    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required.")
    if not admin_raw:
        raise ValueError("TELEGRAM_ADMIN_USER_ID is required.")

    try:
        admin_user_id = int(admin_raw)
    except ValueError as exc:
        raise ValueError("TELEGRAM_ADMIN_USER_ID must be an integer.") from exc

    banner_url = os.getenv("TELEGRAM_BANNER_URL", DEFAULT_BANNER_URL).strip() or DEFAULT_BANNER_URL
    default_workers = _int_from_env(os.getenv("TELEGRAM_DEFAULT_WORKERS", ""), DEFAULT_WORKERS)
    default_target = os.getenv("TELEGRAM_DEFAULT_TARGET", DEFAULT_TARGET).strip() or DEFAULT_TARGET

    session_file = Path(os.getenv("FB_REELS_SESSION_FILE", "fb_reels_cli/session.json"))
    output_dir = Path(os.getenv("FB_REELS_OUTPUT_DIR", "fb_reels_cli/output"))

    return Settings(
        bot_token=token,
        admin_user_id=admin_user_id,
        banner_url=banner_url,
        default_workers=default_workers,
        default_target=default_target,
        session_file=session_file,
        output_dir=output_dir,
    )
