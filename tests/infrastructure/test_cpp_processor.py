"""Tests for the C++ pybind11 image processor adapter."""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from PIL import Image as PILImage

from src.infrastructure.processing.cpp_processor import (
    CppImageProcessor,
    _generate_thumbnail_cpp_sync,
)


@pytest.fixture
def png_bytes() -> bytes:
    img = PILImage.new("RGB", (640, 480), color=(0, 128, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def fake_fast_resize_module():
    def fit_dimensions(src_w: int, src_h: int, max_w: int, max_h: int) -> tuple[int, int]:
        ratio = min(max_w / src_w, max_h / src_h)
        if ratio >= 1:
            return src_w, src_h
        return max(1, int(src_w * ratio)), max(1, int(src_h * ratio))

    def bilinear_resize_bytes(
        src: bytes, src_w: int, src_h: int, channels: int, dst_w: int, dst_h: int
    ) -> bytes:
        mode = "RGBA" if channels == 4 else "RGB"
        resized = PILImage.frombytes(mode, (src_w, src_h), src).resize((dst_w, dst_h))
        return resized.tobytes()

    return SimpleNamespace(
        fit_dimensions=fit_dimensions,
        bilinear_resize_bytes=bilinear_resize_bytes,
    )


def test_generate_thumbnail_cpp_sync(monkeypatch, png_bytes, fake_fast_resize_module):
    monkeypatch.setattr(
        "src.infrastructure.processing.cpp_processor._load_fast_resize_module",
        lambda: fake_fast_resize_module,
    )

    result = _generate_thumbnail_cpp_sync(png_bytes, (128, 128))

    assert result["width"] <= 128
    assert result["height"] <= 128
    assert result["format"] == "PNG"
    assert result["channels"] == 3
    thumb = PILImage.open(io.BytesIO(result["thumbnail_data"]))
    assert thumb.width == result["width"]
    assert thumb.height == result["height"]


@pytest.mark.asyncio
async def test_cpp_processor_generate_thumbnail(monkeypatch, png_bytes, fake_fast_resize_module):
    monkeypatch.setattr(
        "src.infrastructure.processing.cpp_processor._load_fast_resize_module",
        lambda: fake_fast_resize_module,
    )
    monkeypatch.setattr(
        "src.infrastructure.processing.cpp_processor.get_executor",
        lambda *_: None,
    )
    processor = CppImageProcessor(max_workers=1)

    result = await processor.generate_thumbnail(png_bytes, max_size=(128, 128))

    assert result.width <= 128
    assert result.height <= 128
    assert result.channels == 3


@pytest.mark.asyncio
async def test_cpp_processor_extract_metadata(monkeypatch, png_bytes, fake_fast_resize_module):
    monkeypatch.setattr(
        "src.infrastructure.processing.cpp_processor._load_fast_resize_module",
        lambda: fake_fast_resize_module,
    )
    monkeypatch.setattr(
        "src.infrastructure.processing.cpp_processor.get_executor",
        lambda *_: None,
    )
    processor = CppImageProcessor(max_workers=1)

    metadata = await processor.extract_metadata(png_bytes)

    assert metadata["width"] == 640
    assert metadata["height"] == 480
    assert metadata["format"] == "PNG"
