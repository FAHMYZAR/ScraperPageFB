from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, Generic, Optional, TypeVar


K = TypeVar("K")
V = TypeVar("V")


@dataclass(slots=True)
class CacheEntry(Generic[V]):
    value: V
    expires_at: float


class TTLCache(Generic[K, V]):
    def __init__(self, ttl_seconds: int = 300, max_items: int = 64) -> None:
        self.ttl_seconds = max(1, int(ttl_seconds))
        self.max_items = max(1, int(max_items))
        self._store: Dict[K, CacheEntry[V]] = {}

    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired = [key for key, entry in self._store.items() if entry.expires_at <= now]
        for key in expired:
            self._store.pop(key, None)

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        self._purge_expired()
        entry = self._store.get(key)
        if entry is None:
            return default
        return entry.value

    def set(self, key: K, value: V) -> None:
        self._purge_expired()
        if len(self._store) >= self.max_items:
            oldest_key = next(iter(self._store), None)
            if oldest_key is not None:
                self._store.pop(oldest_key, None)
        self._store[key] = CacheEntry(value=value, expires_at=time.monotonic() + self.ttl_seconds)

    def remember(self, key: K, factory: Callable[[], V]) -> V:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        self.set(key, value)
        return value

    def clear(self) -> None:
        self._store.clear()
