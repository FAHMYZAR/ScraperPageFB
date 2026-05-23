from __future__ import annotations

from html import escape
from datetime import datetime
from typing import Iterable, List, Sequence

from CLI_Mode.facebook_reels_cli import format_metric
from models import CdnResult, PageInfo, Reel, SessionStatus
from utils.performance import chunk_text


class Formatter:
    def greeting(self, user_name: str, now: datetime | None = None) -> str:
        current = now or datetime.now()
        hour = current.hour
        if hour < 11:
            greeting = "Selamat Pagi"
        elif hour < 15:
            greeting = "Selamat Siang"
        elif hour < 18:
            greeting = "Selamat Sore"
        else:
            greeting = "Selamat Malam"
        display_name = user_name or "User"
        return f"{greeting}, {display_name}"

    def loading_text(self, stage: str = "Loading", final: bool = False) -> str:
        bar = "▰▰▰▰▱" if not final else "▰▰▰▰▰"
        suffix = "Almost ready..." if not final else "Selesai."
        return f"🎮 {stage}\n{bar} {suffix}"

    def home_menu_text(self, user_name: str) -> str:
        safe_name = escape(user_name or "User")
        return (
            f"<b>🤖 Facebook Reels Bot</b>\n"
            f"{self.greeting(safe_name)}\n\n"
            "Silakan pilih menu di bawah."
        )

    def session_status_text(self, status: SessionStatus) -> str:
        valid_text = "valid" if status.valid is True else "expired" if status.valid is False else "unknown"
        account = status.account_name or "-"
        if status.account_id:
            account = f"{account} ({status.account_id})"

        parts = [
            "📊 Session Status",
            f"Session: {'tersedia' if status.available else 'tidak ada'}",
            f"Valid: {valid_text}",
            f"Akun: {account}",
            f"Source: {status.source or 'unknown'}",
        ]
        if status.reel_count:
            parts.append(f"Reels terdeteksi: {status.reel_count}")
        if status.last_checked_at:
            parts.append(f"Diperiksa: {status.last_checked_at}")
        if status.error:
            parts.append(f"Error: {status.error}")
        return "\n".join(parts)

    def page_info_text(self, page: PageInfo) -> str:
        return (
            "🕷 Page Info\n"
            f"Nama: {page.name or '-'}\n"
            f"Header: {page.title or '-'}\n"
            f"Total item: {page.total_items}\n"
            f"Total reels: {page.total_reels}"
        )

    def reel_card_line(self, reel: Reel) -> str:
        return (
            f"{reel.scan_index or 0}. {reel.title or reel.id}\n"
            f"👁 Views: {format_metric(reel.views, reel.card_views_text)}\n"
            f"❤️ Likes: {format_metric(reel.likes)}\n"
            f"💬 Comments: {format_metric(reel.comments)}\n"
            f"🔁 Shares: {format_metric(reel.shares)}"
        )

    def reel_list_text(self, reels: Sequence[Reel], page: int, total_pages: int, mode: str) -> str:
        mode_label = {
            "popular": "Popular",
            "pick": "Pick Sendiri",
            "newest": "Terbaru",
        }.get(mode, mode)
        header = (
            "📋 Daftar Reels\n"
            f"Mode: {mode_label}\n"
            f"Halaman: {page}/{total_pages}\n\n"
        )
        body = "\n\n".join(self.reel_card_line(reel) for reel in reels)
        return header + body

    def caption(self, title: str, description: str) -> str:
        title = (title or "").strip()
        description = (description or "").strip()
        if not title and not description:
            return ""
        combined = title if not description else f"{title}\n\n{description}" if title else description
        if len(combined) <= 1024:
            return combined
        chunks = chunk_text(combined, limit=1024)
        return chunks[0] if chunks else combined[:1024]

    def download_caption(self, result: CdnResult) -> str:
        return self.caption(result.title, result.description)

    def error_text(self, message: str) -> str:
        return f"⚠️ {message}"
