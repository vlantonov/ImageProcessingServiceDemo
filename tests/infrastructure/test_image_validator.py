"""Tests for image validation security checks."""

from __future__ import annotations

import io
import struct

import pytest
from PIL import Image as PILImage

from src.infrastructure.processing.image_validator import (
    InvalidImageError,
    validate_image_bytes,
)


@pytest.fixture
def valid_png() -> bytes:
    img = PILImage.new("RGB", (100, 80), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def valid_jpeg() -> bytes:
    img = PILImage.new("RGB", (100, 80), color=(0, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_valid_png_passes(valid_png: bytes) -> None:
    validate_image_bytes(valid_png)


def test_valid_jpeg_passes(valid_jpeg: bytes) -> None:
    validate_image_bytes(valid_jpeg)


def test_empty_data_rejected() -> None:
    with pytest.raises(InvalidImageError, match="Empty file"):
        validate_image_bytes(b"")


def test_random_bytes_rejected() -> None:
    with pytest.raises(InvalidImageError, match="Invalid or corrupt"):
        validate_image_bytes(b"this is not an image at all")


def test_truncated_png_rejected(valid_png: bytes) -> None:
    truncated = valid_png[: len(valid_png) // 2]
    with pytest.raises(InvalidImageError):
        validate_image_bytes(truncated)


def test_disallowed_format_rejected() -> None:
    img = PILImage.new("RGB", (10, 10))
    buf = io.BytesIO()
    img.save(buf, format="BMP")
    with pytest.raises(InvalidImageError, match="Unsupported image format"):
        validate_image_bytes(buf.getvalue())


def test_custom_allowed_formats(valid_png: bytes) -> None:
    with pytest.raises(InvalidImageError, match="Unsupported image format"):
        validate_image_bytes(valid_png, allowed_formats={"JPEG"})


def test_webp_passes() -> None:
    img = PILImage.new("RGB", (50, 50))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    validate_image_bytes(buf.getvalue())


def test_crafted_header_with_bad_body_rejected() -> None:
    # PNG magic bytes followed by garbage
    png_header = b"\x89PNG\r\n\x1a\n"
    bad_data = png_header + b"\x00" * 100
    with pytest.raises(InvalidImageError):
        validate_image_bytes(bad_data)


def test_decompression_bomb_rejected() -> None:
    """Create a PNG that claims huge dimensions via header manipulation."""
    # Create a minimal valid PNG, then patch the IHDR to claim enormous dimensions.
    img = PILImage.new("L", (1, 1))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = bytearray(buf.getvalue())

    # IHDR chunk starts at offset 8 (after 8-byte signature), chunk data at +16.
    # Width (4 bytes) at offset 16, Height (4 bytes) at offset 20.
    width_offset = 16
    height_offset = 20
    struct.pack_into(">I", raw, width_offset, 100_000)
    struct.pack_into(">I", raw, height_offset, 100_000)

    with pytest.raises(InvalidImageError):
        validate_image_bytes(bytes(raw))
