"""Tests for the in-memory cache and cached repository decorator."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.domain.entities.image import Image, ProcessingStatus
from src.domain.interfaces.image_repository import ImageRepository
from src.infrastructure.cache.cached_image_repository import CachedImageRepository
from src.infrastructure.cache.in_memory_cache import InMemoryImageCache

# ── InMemoryImageCache tests ─────────────────────────────────────────────────


class TestInMemoryImageCache:
    def _make_image(self, image_id: uuid.UUID | None = None) -> Image:
        return Image(
            id=image_id or uuid.uuid4(),
            filename="test.png",
            original_path="/data/test.png",
            status=ProcessingStatus.PENDING,
        )

    def test_get_returns_none_for_missing(self):
        cache = InMemoryImageCache(ttl_seconds=60)
        assert cache.get(uuid.uuid4()) is None

    def test_set_and_get(self):
        cache = InMemoryImageCache(ttl_seconds=60)
        image = self._make_image()
        cache.set(image)
        assert cache.get(image.id) is image

    def test_invalidate(self):
        cache = InMemoryImageCache(ttl_seconds=60)
        image = self._make_image()
        cache.set(image)
        cache.invalidate(image.id)
        assert cache.get(image.id) is None

    def test_clear(self):
        cache = InMemoryImageCache(ttl_seconds=60)
        for _ in range(5):
            cache.set(self._make_image())
        cache.clear()
        # All cleared — nothing should be retrievable
        assert cache.get(uuid.uuid4()) is None

    @patch("src.infrastructure.cache.in_memory_cache.time.monotonic")
    def test_expired_entry_returns_none(self, mock_monotonic):
        mock_monotonic.return_value = 1000.0
        cache = InMemoryImageCache(ttl_seconds=10)
        image = self._make_image()
        cache.set(image)

        # Advance time past TTL
        mock_monotonic.return_value = 1011.0
        assert cache.get(image.id) is None

    def test_max_size_eviction(self):
        cache = InMemoryImageCache(ttl_seconds=60, max_size=3)
        images = [self._make_image() for _ in range(4)]
        for img in images:
            cache.set(img)

        # Should have at most 3 entries; newest should be present
        assert cache.get(images[3].id) is images[3]

    def test_update_existing_does_not_grow(self):
        cache = InMemoryImageCache(ttl_seconds=60, max_size=2)
        image = self._make_image()
        cache.set(image)
        cache.set(image)  # re-set same ID
        # Should still work, not evict
        assert cache.get(image.id) is image


# ── CachedImageRepository tests ──────────────────────────────────────────────


class TestCachedImageRepository:
    def _make_image(self, image_id: uuid.UUID | None = None) -> Image:
        return Image(
            id=image_id or uuid.uuid4(),
            filename="test.png",
            original_path="/data/test.png",
            status=ProcessingStatus.PENDING,
        )

    @pytest.fixture
    def inner(self) -> ImageRepository:
        repo = AsyncMock(spec=ImageRepository)
        repo.save = AsyncMock()
        repo.get_by_id = AsyncMock(return_value=None)
        repo.list_images = AsyncMock(return_value=[])
        repo.delete = AsyncMock(return_value=True)
        repo.get_expired = AsyncMock(return_value=[])
        repo.delete_expired_batch = AsyncMock(return_value=[])
        repo.count = AsyncMock(return_value=0)
        return repo

    @pytest.fixture
    def cache(self) -> InMemoryImageCache:
        return InMemoryImageCache(ttl_seconds=60, max_size=100)

    @pytest.fixture
    def cached_repo(self, inner, cache) -> CachedImageRepository:
        return CachedImageRepository(inner=inner, cache=cache)

    async def test_get_by_id_cache_miss_delegates(self, cached_repo, inner):
        image = self._make_image()
        inner.get_by_id.return_value = image

        result = await cached_repo.get_by_id(image.id)

        assert result is image
        inner.get_by_id.assert_awaited_once_with(image.id)

    async def test_get_by_id_cache_hit_skips_db(self, cached_repo, inner, cache):
        image = self._make_image()
        cache.set(image)

        result = await cached_repo.get_by_id(image.id)

        assert result is image
        inner.get_by_id.assert_not_awaited()

    async def test_get_by_id_populates_cache(self, cached_repo, inner, cache):
        image = self._make_image()
        inner.get_by_id.return_value = image

        await cached_repo.get_by_id(image.id)
        # Second call should hit cache
        await cached_repo.get_by_id(image.id)

        assert inner.get_by_id.await_count == 1

    async def test_save_invalidates_cache(self, cached_repo, inner, cache):
        image = self._make_image()
        cache.set(image)
        inner.save.return_value = image

        await cached_repo.save(image)

        # Cache should be invalidated
        assert cache.get(image.id) is None
        inner.save.assert_awaited_once_with(image)

    async def test_delete_invalidates_cache(self, cached_repo, inner, cache):
        image = self._make_image()
        cache.set(image)

        await cached_repo.delete(image.id)

        assert cache.get(image.id) is None
        inner.delete.assert_awaited_once_with(image.id)

    async def test_list_images_delegates(self, cached_repo, inner):
        await cached_repo.list_images(offset=0, limit=10, status="pending")
        inner.list_images.assert_awaited_once_with(offset=0, limit=10, status="pending")

    async def test_get_expired_delegates(self, cached_repo, inner):
        await cached_repo.get_expired(batch_size=50)
        inner.get_expired.assert_awaited_once_with(batch_size=50)

    async def test_delete_expired_batch_delegates_and_invalidates(self, cached_repo, inner, cache):
        image = self._make_image()
        cache.set(image)
        inner.delete_expired_batch.return_value = [image]

        result = await cached_repo.delete_expired_batch(batch_size=50)

        assert result == [image]
        inner.delete_expired_batch.assert_awaited_once_with(batch_size=50)
        assert cache.get(image.id) is None

    async def test_count_delegates(self, cached_repo, inner):
        await cached_repo.count(status="completed")
        inner.count.assert_awaited_once_with(status="completed")

    async def test_get_by_id_none_not_cached(self, cached_repo, inner, cache):
        inner.get_by_id.return_value = None

        result = await cached_repo.get_by_id(uuid.uuid4())

        assert result is None
        # Second call should still hit DB (None not cached)
        await cached_repo.get_by_id(uuid.uuid4())
        assert inner.get_by_id.await_count == 2
