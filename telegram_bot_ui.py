from __future__ import annotations

from html import escape
from typing import Any, Dict, List, Optional, Sequence, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from facebook_reels_cli import format_metric, normalize_scan_order
from telegram_media_pipeline import summarize_renditions


def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔐 Login Session Facebook", callback_data="menu:login")],
            [InlineKeyboardButton("🔎 Scan Reels Page", callback_data="menu:scan")],
            [InlineKeyboardButton("🧾 Inspect Reel by ID", callback_data="menu:inspect")],
            [InlineKeyboardButton("📊 Session Status", callback_data="menu:session")],
            [InlineKeyboardButton("🗑️ Clear Session", callback_data="menu:clear")],
            [InlineKeyboardButton("❌ Exit", callback_data="menu:exit")],
        ]
    )


def build_scan_order_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🆕 Terbaru", callback_data="scan:order:newest")],
            [InlineKeyboardButton("🕰️ Paling Lama", callback_data="scan:order:oldest")],
            [InlineKeyboardButton("🔥 Paling Populer", callback_data="scan:order:popular")],
            [InlineKeyboardButton("◀ Kembali", callback_data="menu:home")],
        ]
    )


def build_confirm_keyboard(action_callback: str, cancel_callback: str = "menu:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Lanjutkan", callback_data=action_callback)],
            [InlineKeyboardButton("◀ Kembali", callback_data=cancel_callback)],
            [InlineKeyboardButton("❌ Exit", callback_data="menu:exit")],
        ]
    )


def build_scan_result_keyboard(results: List[Dict[str, Any]], max_buttons: int = 30) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    current_row: List[InlineKeyboardButton] = []

    for idx, _ in enumerate(results[:max_buttons], 1):
        current_row.append(InlineKeyboardButton(str(idx), callback_data=f"scan:pick:{idx - 1}"))
        if len(current_row) == 5:
            rows.append(current_row)
            current_row = []

    if current_row:
        rows.append(current_row)

    rows.append([InlineKeyboardButton("🔁 Scan Ulang", callback_data="menu:scan")])
    rows.append([InlineKeyboardButton("◀ Kembali", callback_data="menu:home"), InlineKeyboardButton("❌ Exit", callback_data="menu:exit")])
    return InlineKeyboardMarkup(rows)


def build_detail_keyboard(
    resolution_buttons: Optional[Sequence[Tuple[str, str]]] = None,
    show_send_best: bool = False,
) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    if show_send_best:
        rows.append([InlineKeyboardButton("🎬 Kirim Video (Best)", callback_data="media:best")])

    if resolution_buttons:
        current_row: List[InlineKeyboardButton] = []
        for label, callback_data in resolution_buttons:
            current_row.append(InlineKeyboardButton(label, callback_data=callback_data))
            if len(current_row) == 2:
                rows.append(current_row)
                current_row = []
        if current_row:
            rows.append(current_row)

    rows.append([InlineKeyboardButton("🔙 Daftar Reel", callback_data="scan:results")])
    rows.append(
        [
            InlineKeyboardButton("🏠 Menu Utama", callback_data="menu:home"),
            InlineKeyboardButton("❌ Exit", callback_data="menu:exit"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_clear_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Ya, Hapus Session", callback_data="session:clear:yes")],
            [InlineKeyboardButton("◀ Batal", callback_data="menu:home")],
        ]
    )


def format_main_menu_text() -> str:
    return (
        "<b>🤖 Facebook Reels Scraper Bot</b>\n"
        "Single-thread menu aktif. Pilih aksi dari tombol di bawah.\n\n"
        "Tips:\n"
        "• Login session Facebook dulu via cookie string\n"
        "• Lalu scan reels, pilih nomor untuk detail layer-2"
    )


def format_scan_results_text(
    results: List[Dict[str, Any]],
    target_url: str,
    order_label: str,
    max_items_in_text: int = 20,
    max_pickable: int = 30,
) -> str:
    order_map = {
        "newest": "Terbaru",
        "oldest": "Paling Lama",
        "popular": "Paling Populer",
    }
    order_key = normalize_scan_order(order_label)
    friendly_order = order_map.get(order_key, order_label)

    header = (
        "📋 Hasil Scan Reels\n"
        f"🔗 Target: {target_url}\n"
        f"🧭 Urutan: {friendly_order}\n"
        f"📦 Total: {len(results)} reel\n\n"
    )

    lines: List[str] = []
    for idx, item in enumerate(results, 1):
        reel_id = str(item.get("reel_id", "-"))
        views = format_metric(None, item.get("card_views", ""))
        likes = format_metric(item.get("likes"), item.get("likes_raw"))
        comments = format_metric(item.get("comments"), item.get("comments_raw"))
        shares = format_metric(item.get("shares"), item.get("shares_raw"))
        title = str(item.get("title", "-") or "-")
        description = str(item.get("description", "-") or "-")
        cdn_quality = str(item.get("best_cdn_quality", "-") or "-")
        cdn_url = str(item.get("best_cdn_url", "-") or "-")

        lines.append(
            f"{idx}. 🎞️ {reel_id}\n"
            f"URL: {item.get('url', '-')}\n"
            f"👀 {views} • 👍 {likes} • 💬 {comments} • ↪️ {shares}\n"
            f"🏷️ CDN: {cdn_quality}\n"
            f"🌐 CDN URL: {cdn_url}\n"
            f"📝 Title: {title}\n"
            f"📄 Desc: {description}"
        )

    lines.append("\nPilih nomor reel dari tombol untuk buka detail layer-2.")
    if len(results) > max_pickable:
        lines.append(
            f"Hanya {max_pickable} reel pertama yang diberi tombol nomor. "
            "Gunakan menu Inspect by ID untuk reel lainnya."
        )
    return header + "\n\n".join(lines)


def format_detail_text(detail: Dict[str, Any]) -> str:
    reel_id = str(detail.get("reel_id", "-"))
    url = str(detail.get("url", "-"))
    likes = format_metric(detail.get("likes"), detail.get("likes_raw"))
    comments = format_metric(detail.get("comments"), detail.get("comments_raw"))
    shares = format_metric(detail.get("shares"), detail.get("shares_raw"))
    duration = detail.get("duration_seconds")
    best_quality = str(detail.get("best_cdn_quality", "-") or "-")
    best_url = str(detail.get("best_cdn_url", "-") or "-")
    description = str(detail.get("description", "-") or "-")

    duration_text = "-" if duration is None else f"{duration} detik"
    renditions = detail.get("renditions", []) or []
    rendition_lines = summarize_renditions(renditions, limit=len(renditions) if renditions else 0)
    rendition_text = "Tidak ada daftar rendition." if not rendition_lines else "\n".join(rendition_lines)

    return (
        "🎬 Detail Reel (Layer 2)\n"
        f"ID: {reel_id}\n"
        f"URL: {url}\n"
        f"👍 {likes} • 💬 {comments} • ↪️ {shares}\n"
        f"⏱️ Duration: {duration_text}\n"
        f"🏷️ CDN Quality: {best_quality}\n"
        f"🌐 CDN URL: {best_url}\n\n"
        f"📝 Description:\n{description}\n\n"
        "📚 Daftar CDN / Rendition\n"
        f"{rendition_text}"
    )


def format_session_status_text(
    source: str,
    cookie_count: int,
    account_name: str,
    account_id: str,
    usable: Optional[bool],
    reel_count: Optional[int] = None,
    error: str = "",
) -> str:
    if usable is True:
        state = f"✅ usable ({reel_count or 0} reel cards terdeteksi)"
    elif usable is False:
        state = "⚠️ looks logged out / invalid"
    else:
        state = "ℹ️ belum diverifikasi"

    identity = account_name or "-"
    if account_id:
        identity = f"{identity} ({escape(account_id)})"

    text = (
        "<b>📊 Session Status</b>\n"
        f"Source: <code>{escape(source or 'unknown')}</code>\n"
        f"Cookies: <b>{cookie_count}</b>\n"
        f"Account: {escape(identity)}\n"
        f"State: {state}"
    )
    if error:
        text += f"\nError: {escape(error)}"
    return text
