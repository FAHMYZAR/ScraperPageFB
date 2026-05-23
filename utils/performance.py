from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple, TypeVar


T = TypeVar("T")


def clamp_concurrency(requested: int, hard_limit: int = 4) -> int:
    try:
        value = int(requested)
    except (TypeError, ValueError):
        return 1
    return max(1, min(value, hard_limit))


def chunk_text(text: str, limit: int = 3900) -> List[str]:
    if not text:
        return [""]

    chunks: List[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append(current.rstrip("\n"))
                current = ""
            for start in range(0, len(line), limit):
                part = line[start:start + limit]
                if part:
                    chunks.append(part.rstrip("\n"))
            continue

        if current and len(current) + len(line) > limit:
            chunks.append(current.rstrip("\n"))
            current = line
        else:
            current += line

    if current:
        chunks.append(current.rstrip("\n"))

    return [chunk for chunk in chunks if chunk]


def paginate(items: Sequence[T], page: int, page_size: int) -> Tuple[List[T], int, int]:
    safe_page_size = max(1, int(page_size))
    total = len(items)
    total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
    safe_page = min(max(1, int(page)), total_pages)
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    return list(items[start:end]), safe_page, total_pages
