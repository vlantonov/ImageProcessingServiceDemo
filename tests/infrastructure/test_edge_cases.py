"""Edge-case tests: failures, timeouts, and concurrent access in infrastructure."""

from __future__ import annotations

import asyncio
import io
import threading
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image as PILImage

from src.domain.entities.image import Image, ProcessingStatus
from src.domain.interfaces.image_repository import ImageRepository
from src.infrastructure.cache.cached_image_repository import CachedImageRepository
from src.infrastructure.cache.in_memory_cache import InMemoryImageCache
from src.infrastructure.processing.pillow_processor import PillowImageProcessor
from src.infrastructure.storage.local_image_storage import LocalImageStorage

# ── LocalImageStorage failure edge cases ─────────────────────────────────────


class TestLocalStorageFailures:
    @pytest.fixture
    def storage(self, tmp_path) -> LocalImageStorage:
        return LocalImageStorage(str(tmp_path / "images"))

    async def test_retrieve_nonexistent_file(self, storage):
        with pytest.raises(FileNotFoundError):
            await storage.retrieve("/nonexistent/path/file.png")

    async def test_delete_nonexistent_returns_false(self, storage):
        result = await storage.delete("/nonexistent/path/file.png")
        assert result is False

    async def test_store_path_traversal_stripped(self, storage):
        """Path components are stripped; file is stored safely using basename only."""
        path = await storage.store("../../etc/passwd", b"safe-data")
        assert "passwd" in path
        data = await storage.retrieve(path)
        assert data == b"safe-data"

    async def test_store_absolute_path_uses_only_basename(self, storage):
        path = await storage.store("/some/absolute/path/image.png", b"data")
        assert "image.png" in path
        retrieved = await storage.retrieve(path)
        assert retrieved == b"data"

    async def test_store_empty_data(self, storage):
        path = await storage.store("empty.png", b"")
        data = await storage.retrieve(path)
        assert data == b""

    async def test_concurrent_store_same_filename(self, storage):
        """Concurrent stores with same filename but different data get unique paths."""
        tasks = [storage.store("concurrent.png", f"data-{i}".encode()) for i in range(10)]
        paths = await asyncio.gather(*tasks)
        # All paths should be unique (different content hashes)
        assert len(set(paths)) == 10

    async def test_store_then_delete_then_retrieve_fails(self, storage):
        path = await storage.store("temp.png", b"temporary")
        assert await storage.delete(path) is True
        with pytest.raises(FileNotFoundError):
            await storage.retrieve(path)

    async def test_concurrent_delete_same_file(self, storage):
        """Only one of concurrent deletes should return True."""
        path = await storage.store("one.png", b"data")
        results = await asyncio.gather(
            storage.delete(path),
            storage.delete(path),
            return_exceptions=True,
        )
        true_count = sum(1 for r in results if r is True)
        false_count = sum(1 for r in results if r is False)
        assert true_count + false_count == 2
        assert true_count >= 1  # At least one succeeds


# ── PillowImageProcessor failure edge cases ──────────────────────────────────


class TestPillowProcessorFailures:
    @pytest.fixture
    def processor(self) -> PillowImageProcessor:
        return PillowImageProcessor(max_workers=2)

    @pytest.fixture
    def png_bytes(self) -> bytes:
        img = PILImage.new("RGB", (640, 480), color=(0, 128, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def test_corrupt_image_data_raises(self, processor):
        with pytest.raises((OSError, ValueError)):
            await processor.generate_thumbnail(b"not-an-image")

    async def test_empty_bytes_raises(self, processor):
        with pytest.raises((OSError, ValueError)):
            await processor.generate_thumbnail(b"")

    async def test_truncated_image_raises(self, processor, png_bytes):
        truncated = png_bytes[: len(png_bytes) // 4]
        with pytest.raises((OSError, ValueError)):
            await processor.generate_thumbnail(truncated)

    async def test_extract_metadata_corrupt_data_raises(self, processor):
        with pytest.raises((OSError, ValueError)):
            await processor.extract_metadata(b"not-an-image")

    async def test_concurrent_thumbnail_generation(self, processor, png_bytes):
        """Multiple concurrent thumbnail requests should all succeed."""
        tasks = [processor.generate_thumbnail(png_bytes, max_size=(64, 64)) for _ in range(5)]
        results = await asyncio.gather(*tasks)
        assert len(results) == 5
        for result in results:
            assert result.width <= 64
            assert result.height <= 64

    async def test_thumbnail_very_small_image(self, processor):
        """1x1 pixel image should produce valid thumbnail."""
        img = PILImage.new("RGB", (1, 1), color=(255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()

        result = await processor.generate_thumbnail(data, max_size=(256, 256))
        assert result.width == 1
        assert result.height == 1

    async def test_thumbnail_rgba_image(self, processor):
        """RGBA image should be handled correctly."""
        img = PILImage.new("RGBA", (200, 150), color=(255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()

        result = await processor.generate_thumbnail(data, max_size=(100, 100))
        assert result.width <= 100
        assert result.height <= 100
        assert result.channels == 4


# ── InMemoryImageCache concurrent edge cases ─────────────────────────────────


class TestCacheConcurrency:
    def _make_image(self, image_id: uuid.UUID | None = None) -> Image:
        return Image(
            id=image_id or uuid.uuid4(),
            filename="test.png",
            original_path="/data/test.png",
            status=ProcessingStatus.PENDING,
        )

    def test_concurrent_set_and_get(self):
        """Thread-safe set/get under concurrent access."""
        cache = InMemoryImageCache(ttl_seconds=60, max_size=100)
        images = [self._make_image() for _ in range(50)]
        errors: list[Exception] = []

        def writer():
            try:
                for img in images:
                    cache.set(img)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for img in images:
                    cache.get(img.id)  # May or may not find it
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors

    def test_concurrent_set_and_invalidate(self):
        """Concurrent set and invalidate should not corrupt state."""
        cache = InMemoryImageCache(ttl_seconds=60, max_size=100)
        image = self._make_image()
        errors: list[Exception] = []

        def setter():
            try:
                for _ in range(100):
                    cache.set(image)
            except Exception as e:
                errors.append(e)

        def invalidator():
            try:
                for _ in range(100):
                    cache.invalidate(image.id)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=setter),
            threading.Thread(target=invalidator),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors

    def test_concurrent_eviction_under_pressure(self):
        """Many threads writing to a small cache should not raise."""
        cache = InMemoryImageCache(ttl_seconds=60, max_size=5)
        errors: list[Exception] = []

        def writer():
            try:
                for _ in range(50):
                    cache.set(self._make_image())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors

    def test_concurrent_clear(self):
        """Concurrent clears and sets should not raise."""
        cache = InMemoryImageCache(ttl_seconds=60, max_size=100)
        errors: list[Exception] = []

        def writer():
            try:
                for _ in range(50):
                    cache.set(self._make_image())
            except Exception as e:
                errors.append(e)

        def clearer():
            try:
                for _ in range(20):
                    cache.clear()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=clearer),
            threading.Thread(target=writer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors

    @patch("src.infrastructure.cache.in_memory_cache.time.monotonic")
    def test_all_entries_expired_eviction(self, mock_monotonic):
        """When all entries are expired, _evict_expired clears them all."""
        mock_monotonic.return_value = 1000.0
        cache = InMemoryImageCache(ttl_seconds=5, max_size=3)
        for _ in range(3):
            cache.set(self._make_image())

        mock_monotonic.return_value = 1010.0  # All expired

        # This triggers eviction since cache is full
        new_img = self._make_image()
        cache.set(new_img)
        assert cache.get(new_img.id) is new_img


# ── CachedImageRepository failure edge cases ────────────────────────────────


class TestCachedRepositoryFailures:
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

    async def test_inner_save_raises_cache_retains_stale_entry(self, cached_repo, inner, cache):
        """If inner save raises, cache still has the old entry (invalidation is post-save)."""
        image = self._make_image()
        cache.set(image)
        inner.save.side_effect = RuntimeError("DB error")

        with pytest.raises(RuntimeError):
            await cached_repo.save(image)

        # Cache still has old entry because invalidation happens after inner.save
        assert cache.get(image.id) is image

    async def test_inner_get_by_id_raises_propagates(self, cached_repo, inner):
        """DB errors on get_by_id should propagate, not be cached."""
        inner.get_by_id.side_effect = RuntimeError("DB timeout")

        with pytest.raises(RuntimeError):
            await cached_repo.get_by_id(uuid.uuid4())

    async def test_inner_delete_raises_cache_invalidated(self, cached_repo, inner, cache):
        """Cache is invalidated before inner.delete, so entry is gone even if inner raises."""
        image = self._make_image()
        cache.set(image)
        inner.delete.side_effect = RuntimeError("DB error")

        with pytest.raises(RuntimeError):
            await cached_repo.delete(image.id)

        # Cache was invalidated before the inner call
        assert cache.get(image.id) is None

    async def test_concurrent_get_by_id_cache_miss(self, inner, cache):
        """Concurrent get_by_id calls on a cold cache should not error."""
        image = self._make_image()
        inner.get_by_id.return_value = image
        cached_repo = CachedImageRepository(inner=inner, cache=cache)

        results = await asyncio.gather(*[cached_repo.get_by_id(image.id) for _ in range(10)])

        assert all(r is image for r in results)

    async def test_delete_expired_batch_partial_cache_invalidation(self, cached_repo, inner, cache):
        """All returned images should be invalidated from cache."""
        images = [self._make_image() for _ in range(3)]
        for img in images:
            cache.set(img)
        inner.delete_expired_batch.return_value = images

        await cached_repo.delete_expired_batch(batch_size=10)

        for img in images:
            assert cache.get(img.id) is None
