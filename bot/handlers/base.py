from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.keyboards.menu_keyboard import MenuKeyboardFactory
from bot.states import UserState
from services import FacebookScraper, MediaSender, SessionManager, VideoDownloader
from utils import Formatter


@dataclass(slots=True)
class BotServices:
    session_manager: SessionManager
    scraper: FacebookScraper
    downloader: VideoDownloader
    media_sender: MediaSender
    formatter: Formatter
    keyboards: MenuKeyboardFactory
    default_target: str


def get_user_state(context) -> UserState:
    state = context.user_data.get("state")
    if not isinstance(state, UserState):
        state = UserState()
        context.user_data["state"] = state
    return state
