"""Tests for the PillowImageProcessor."""

from __future__ import annotations

import io

import pytest
from PIL import Image as PILImage

from src.infrastructure.processing.pillow_processor import (
    PillowImageProcessor,
    _extract_metadata_sync,
    _generate_thumbnail_sync,
    get_executor,
    shutdown_executor,
)


@pytest.fixture
def processor() -> PillowImageProcessor:
    return PillowImageProcessor(max_workers=2)


@pytest.fixture
def png_bytes() -> bytes:
    img = PILImage.new("RGB", (640, 480), color=(0, 128, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_generate_thumbnail(processor, png_bytes):
    result = await processor.generate_thumbnail(png_bytes, max_size=(128, 128))

    assert result.width <= 128
    assert result.height <= 128
    assert result.channels == 3
    assert result.format == "PNG"
    assert len(result.thumbnail_data) > 0

    # Verify the thumbnail is a valid image
    thumb_img = PILImage.open(io.BytesIO(result.thumbnail_data))
    assert thumb_img.width <= 128
    assert thumb_img.height <= 128


@pytest.mark.asyncio
async def test_extract_metadata(processor, png_bytes):
    meta = await processor.extract_metadata(png_bytes)

    assert meta["width"] == 640
    assert meta["height"] == 480
    assert meta["format"] == "PNG"
    assert meta["channels"] == 3
    assert meta["size_bytes"] == len(png_bytes)


# ── Direct tests for sync worker functions ───────────────────────────────────
# These run in-process so coverage can track them (ProcessPoolExecutor runs
# in child processes invisible to the coverage collector).


class TestGenerateThumbnailSync:
    def test_basic_thumbnail(self, png_bytes):
        result = _generate_thumbnail_sync(png_bytes, (128, 128))

        assert result["width"] <= 128
        assert result["height"] <= 128
        assert result["format"] == "PNG"
        assert result["channels"] == 3
        assert result["size_bytes"] == len(png_bytes)
        assert len(result["thumbnail_data"]) > 0

        # Verify output is a valid image
        thumb = PILImage.open(io.BytesIO(result["thumbnail_data"]))
        assert thumb.width == result["width"]
        assert thumb.height == result["height"]

    def test_preserves_aspect_ratio(self):
        img = PILImage.new("RGB", (800, 400), color=(255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()

        result = _generate_thumbnail_sync(data, (200, 200))

        assert result["width"] == 200
        assert result["height"] == 100

    def test_rgba_image(self):
        img = PILImage.new("RGBA", (300, 200), color=(0, 255, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()

        result = _generate_thumbnail_sync(data, (100, 100))

        assert result["channels"] == 4
        assert result["width"] <= 100
        assert result["height"] <= 100

    def test_already_small_image(self):
        img = PILImage.new("RGB", (50, 30))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()

        result = _generate_thumbnail_sync(data, (256, 256))

        assert result["width"] == 50
        assert result["height"] == 30

    def test_jpeg_format_preserved(self):
        img = PILImage.new("RGB", (400, 300))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        data = buf.getvalue()

        result = _generate_thumbnail_sync(data, (100, 100))

        assert result["format"] == "JPEG"

    def test_corrupt_data_raises(self):
        with pytest.raises((OSError, ValueError)):
            _generate_thumbnail_sync(b"not-an-image", (128, 128))


class TestExtractMetadataSync:
    def test_basic_metadata(self, png_bytes):
        meta = _extract_metadata_sync(png_bytes)

        assert meta["width"] == 640
        assert meta["height"] == 480
        assert meta["format"] == "PNG"
        assert meta["channels"] == 3
        assert meta["size_bytes"] == len(png_bytes)
        assert meta["mode"] == "RGB"

    def test_rgba_metadata(self):
        img = PILImage.new("RGBA", (100, 50))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()

        meta = _extract_metadata_sync(data)

        assert meta["width"] == 100
        assert meta["height"] == 50
        assert meta["channels"] == 4
        assert meta["mode"] == "RGBA"

    def test_grayscale_metadata(self):
        img = PILImage.new("L", (200, 150))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()

        meta = _extract_metadata_sync(data)

        assert meta["channels"] == 1
        assert meta["mode"] == "L"

    def test_corrupt_data_raises(self):
        with pytest.raises((OSError, ValueError)):
            _extract_metadata_sync(b"bad-data")


# ── Executor lifecycle tests ─────────────────────────────────────────────────


class TestExecutorLifecycle:
    def test_shutdown_and_recreate(self):
        # Ensure an executor exists
        executor = get_executor(max_workers=1)
        assert executor is not None

        # Shutdown should succeed
        shutdown_executor()

        # A new call should create a fresh executor
        new_executor = get_executor(max_workers=1)
        assert new_executor is not None

        # Cleanup
        shutdown_executor()

    def test_shutdown_when_no_executor(self):
        shutdown_executor()  # ensure clean state
        shutdown_executor()  # should be a no-op, not raise
