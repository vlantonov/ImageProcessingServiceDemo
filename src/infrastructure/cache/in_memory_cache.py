"""In-memory TTL cache for image metadata.

Uses a simple dictionary with expiry timestamps. In production, this could be
swapped for a Redis-backed implementation without changing the repository
decorator interface.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from src.domain.entities.image import Image


@dataclass
class _CacheEntry:
    image: Image
    expires_at: float


@dataclass
class InMemoryImageCache:
    """Async-safe in-memory cache with TTL-based expiration."""

    ttl_seconds: float = 60.0
    max_size: int = 1024
    _store: dict[uuid.UUID, _CacheEntry] = field(default_factory=dict, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def get(self, image_id: uuid.UUID) -> Image | None:
        async with self._lock:
            entry = self._store.get(image_id)
            if entry is None:
                return None
            if time.monotonic() > entry.expires_at:
                del self._store[image_id]
                return None
            return entry.image

    async def set(self, image: Image) -> None:
        async with self._lock:
            if len(self._store) >= self.max_size and image.id not in self._store:
                self._evict_expired()
                if len(self._store) >= self.max_size:
                    self._evict_oldest()
            self._store[image.id] = _CacheEntry(
                image=image,
                expires_at=time.monotonic() + self.ttl_seconds,
            )

    async def invalidate(self, image_id: uuid.UUID) -> None:
        async with self._lock:
            self._store.pop(image_id, None)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, v in self._store.items() if now > v.expires_at]
        for k in expired:
            del self._store[k]

    def _evict_oldest(self) -> None:
        if not self._store:
            return
        oldest_key = min(self._store, key=lambda k: self._store[k].expires_at)
        del self._store[oldest_key]
