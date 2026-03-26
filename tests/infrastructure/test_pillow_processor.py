"""Tests for the PillowImageProcessor."""

from __future__ import annotations

import io

import pytest
from PIL import Image as PILImage

from src.infrastructure.processing.pillow_processor import PillowImageProcessor


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
