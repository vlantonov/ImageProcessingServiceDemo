"""Image validation to prevent malicious file exploits against Pillow.

Validates that uploaded bytes are legitimate images before storage or
processing, mitigating decompression bombs, truncated-file attacks,
and other CVEs targeting image parsers.
"""

from __future__ import annotations

import io
import logging

from PIL import Image as PILImage
from PIL import ImageFile

# Reject truncated images — never set to True, as it allows partial
# parsing of corrupt/malicious files that can trigger Pillow CVEs.
ImageFile.LOAD_TRUNCATED_IMAGES = False

logger = logging.getLogger(__name__)

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "TIFF"}

# 100 megapixels — generous for legitimate photos, blocks decompression bombs.
MAX_IMAGE_PIXELS = 100_000_000


class InvalidImageError(Exception):
    """Raised when uploaded bytes fail image validation."""


def validate_image_bytes(data: bytes, allowed_formats: set[str] | None = None) -> None:
    """Validate that *data* is a genuine, safe image file.

    Raises ``InvalidImageError`` if the data is not a valid image, uses a
    disallowed format, or exceeds pixel-count limits (decompression bomb).
    """
    if allowed_formats is None:
        allowed_formats = ALLOWED_FORMATS

    if not data:
        raise InvalidImageError("Empty file")

    old_max = PILImage.MAX_IMAGE_PIXELS
    try:
        PILImage.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

        img = PILImage.open(io.BytesIO(data))

        # Detect format before full decode — fast rejection of unsupported types.
        fmt = (img.format or "").upper()
        if fmt not in allowed_formats:
            raise InvalidImageError(f"Unsupported image format: {fmt or 'unknown'}")

        # Full decode + integrity check.  This calls Pillow's verify() which
        # reads the full file and validates checksums / structure without
        # loading pixel data into memory.
        img.verify()

        # After verify() the image object is unusable, so re-open and load
        # to ensure pixel data is decodable (catches truncated payloads).
        img = PILImage.open(io.BytesIO(data))
        img.load()

    except InvalidImageError:
        raise
    except PILImage.DecompressionBombError as exc:
        raise InvalidImageError(f"Image exceeds pixel limit: {exc}") from exc
    except Exception as exc:
        raise InvalidImageError(f"Invalid or corrupt image file: {exc}") from exc
    finally:
        PILImage.MAX_IMAGE_PIXELS = old_max
