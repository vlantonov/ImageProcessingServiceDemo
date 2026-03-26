"""Pillow-based image processor.

CPU-bound work is offloaded to a ProcessPoolExecutor so the async event loop
stays responsive under heavy load.  This is the key parallelization pattern
required by the role.
"""

from __future__ import annotations

import asyncio
import io
from concurrent.futures import ProcessPoolExecutor

from PIL import Image as PILImage

from src.domain.interfaces.image_processor import ImageProcessor, ProcessingResult

# Module-level executor shared across requests.
_executor: ProcessPoolExecutor | None = None


def get_executor(max_workers: int = 4) -> ProcessPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ProcessPoolExecutor(max_workers=max_workers)
    return _executor


# ── Free functions executed in worker processes ──────────────────────────────


def _generate_thumbnail_sync(data: bytes, max_size: tuple[int, int]) -> dict:
    """Pure function — safe to run in a subprocess."""
    img = PILImage.open(io.BytesIO(data))
    img.thumbnail(max_size)

    buf = io.BytesIO()
    out_format = img.format or "PNG"
    img.save(buf, format=out_format)
    thumb_bytes = buf.getvalue()

    channels = len(img.getbands())
    return {
        "thumbnail_data": thumb_bytes,
        "width": img.width,
        "height": img.height,
        "format": out_format,
        "size_bytes": len(data),
        "channels": channels,
    }


def _extract_metadata_sync(data: bytes) -> dict:
    img = PILImage.open(io.BytesIO(data))
    return {
        "width": img.width,
        "height": img.height,
        "format": img.format,
        "size_bytes": len(data),
        "channels": len(img.getbands()),
        "mode": img.mode,
    }


# ── Async wrapper ────────────────────────────────────────────────────────────


class PillowImageProcessor(ImageProcessor):
    def __init__(self, max_workers: int = 4) -> None:
        self._max_workers = max_workers

    async def generate_thumbnail(
        self, image_data: bytes, max_size: tuple[int, int] = (256, 256)
    ) -> ProcessingResult:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            get_executor(self._max_workers),
            _generate_thumbnail_sync,
            image_data,
            max_size,
        )
        return ProcessingResult(**result)

    async def extract_metadata(self, image_data: bytes) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            get_executor(self._max_workers),
            _extract_metadata_sync,
            image_data,
        )
