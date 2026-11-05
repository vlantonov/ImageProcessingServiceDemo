"""Caching decorator for ImageRepository.

Wraps any ImageRepository implementation with an in-memory TTL cache for
single-entity lookups (get_by_id). Write operations (save, delete)
automatically invalidate the cache to maintain consistency.
"""

from __future__ import annotations

import logging
import uuid

from src.domain.entities.image import Image
from src.domain.interfaces.image_repository import IdempotencyRecord, ImageRepository
from src.infrastructure.cache.in_memory_cache import InMemoryImageCache

logger = logging.getLogger(__name__)


class CachedImageRepository(ImageRepository):
    """Repository decorator that caches get_by_id results."""

    def __init__(self, inner: ImageRepository, cache: InMemoryImageCache) -> None:
        self._inner = inner
        self._cache = cache

    async def save(self, image: Image) -> Image:
        result = await self._inner.save(image)
        await self._cache.invalidate(image.id)
        return result

    async def get_by_id(self, image_id: uuid.UUID) -> Image | None:
        cached = await self._cache.get(image_id)
        if cached is not None:
            logger.debug("Cache hit: image=%s", image_id)
            return cached
        logger.debug("Cache miss: image=%s", image_id)
        image = await self._inner.get_by_id(image_id)
        if image is not None:
            await self._cache.set(image)
        return image

    async def list_images(
        self, *, offset: int = 0, limit: int = 50, status: str | None = None
    ) -> list[Image]:
        return await self._inner.list_images(offset=offset, limit=limit, status=status)

    async def delete(self, image_id: uuid.UUID) -> bool:
        await self._cache.invalidate(image_id)
        return await self._inner.delete(image_id)

    async def get_expired(self, batch_size: int = 100) -> list[Image]:
        return await self._inner.get_expired(batch_size=batch_size)

    async def delete_expired_batch(self, batch_size: int = 100) -> list[Image]:
        deleted = await self._inner.delete_expired_batch(batch_size=batch_size)
        for image in deleted:
            await self._cache.invalidate(image.id)
        return deleted

    async def count(self, *, status: str | None = None) -> int:
        return await self._inner.count(status=status)

    async def get_idempotency_record(self, *, scope: str, key: str) -> IdempotencyRecord | None:
        return await self._inner.get_idempotency_record(scope=scope, key=key)

    async def create_idempotency_record(
        self,
        *,
        scope: str,
        key: str,
        request_hash: str,
        image_id: uuid.UUID | None = None,
    ) -> bool:
        return await self._inner.create_idempotency_record(
            scope=scope,
            key=key,
            request_hash=request_hash,
            image_id=image_id,
        )

    async def complete_idempotency_record(
        self,
        *,
        scope: str,
        key: str,
        image_id: uuid.UUID,
    ) -> None:
        await self._inner.complete_idempotency_record(scope=scope, key=key, image_id=image_id)

    async def delete_idempotency_record(self, *, scope: str, key: str) -> None:
        await self._inner.delete_idempotency_record(scope=scope, key=key)
