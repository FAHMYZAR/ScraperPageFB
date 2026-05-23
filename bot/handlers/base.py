from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bot.keyboards.menu_keyboard import MenuKeyboardFactory
from bot.states import UserState
from services import FacebookScraper, FacebookUrlResolver, MediaSender, SessionManager, VideoDownloader
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
    banner_url: str
    session_dir: Path
    temp_dir: Path
    default_workers: int
    resolver: FacebookUrlResolver
    session_managers: dict[int, SessionManager]
    scrapers: dict[int, FacebookScraper]
    downloaders: dict[int, VideoDownloader]

    def user_id_for_update(self, update) -> int:
        if update.effective_user:
            return int(update.effective_user.id)
        if update.effective_chat:
            return int(update.effective_chat.id)
        return 0

    def session_for_update(self, update) -> SessionManager:
        user_id = self.user_id_for_update(update)
        manager = self.session_managers.get(user_id)
        if manager is None:
            manager = SessionManager(self.session_dir / f"{user_id}.json")
            if not manager.available:
                self._bootstrap_user_session(manager)
            self.session_managers[user_id] = manager
        return manager

    def _bootstrap_user_session(self, manager: SessionManager) -> None:
        sources = [self.session_manager]
        fallback_path = Path("CLI_Mode") / "fb_reels_cli" / "session.json"
        if fallback_path != self.session_manager.session_file:
            sources.append(SessionManager(fallback_path))
        for source in sources:
            if not source.available:
                continue
            try:
                manager.import_from_manager(source, source_name=source.source)
                return
            except Exception:
                continue

    def scraper_for_update(self, update) -> FacebookScraper:
        user_id = self.user_id_for_update(update)
        scraper = self.scrapers.get(user_id)
        if scraper is None:
            scraper = FacebookScraper(self.session_for_update(update), self.default_target, self.default_workers)
            self.scrapers[user_id] = scraper
        return scraper

    def downloader_for_update(self, update) -> VideoDownloader:
        user_id = self.user_id_for_update(update)
        downloader = self.downloaders.get(user_id)
        if downloader is None:
            downloader = VideoDownloader(self.session_for_update(update))
            self.downloaders[user_id] = downloader
        return downloader

    def temp_dir_for_update(self, update) -> Path:
        path = self.temp_dir / str(self.user_id_for_update(update))
        path.mkdir(parents=True, exist_ok=True)
        return path


def get_user_state(context) -> UserState:
    state = context.user_data.get("state")
    if not isinstance(state, UserState):
        state = UserState()
        context.user_data["state"] = state
    return state
