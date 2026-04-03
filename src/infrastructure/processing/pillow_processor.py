"""Pillow-based image processor.

CPU-bound work is offloaded to a ProcessPoolExecutor so the async event loop
stays responsive under heavy load.  This is the key parallelization pattern
required by the role.
"""

from __future__ import annotations

import asyncio
import io
import logging
from concurrent.futures import ProcessPoolExecutor

from PIL import Image as PILImage
from PIL import ImageFile

from src.domain.interfaces.image_processor import ImageProcessor, ProcessingResult

logger = logging.getLogger(__name__)

# Security: never load truncated/corrupt images — prevents CVE exploitation.
ImageFile.LOAD_TRUNCATED_IMAGES = False

# Module-level executor shared across requests.
_executor: ProcessPoolExecutor | None = None


def get_executor(max_workers: int = 4) -> ProcessPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ProcessPoolExecutor(max_workers=max_workers)
    return _executor


def shutdown_executor() -> None:
    """Shut down the module-level executor, releasing worker processes."""
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=True)
        _executor = None


_SHUTDOWN_TIMEOUT_SECONDS = 30


async def async_shutdown_executor() -> None:
    """Shut down the executor without blocking the event loop.

    Waits up to ``_SHUTDOWN_TIMEOUT_SECONDS`` for in-flight tasks to finish.
    If they don't complete in time, the executor is force-cancelled.
    """
    global _executor
    if _executor is None:
        return

    executor = _executor
    _executor = None

    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, executor.shutdown, True),
            timeout=_SHUTDOWN_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning(
            "Executor did not shut down within %ds, forcing cancellation",
            _SHUTDOWN_TIMEOUT_SECONDS,
        )
        executor.shutdown(wait=False, cancel_futures=True)


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
    def __init__(
        self, max_workers: int = 4, thumbnail_max_size: tuple[int, int] = (256, 256)
    ) -> None:
        self._max_workers = max_workers
        self._thumbnail_max_size = thumbnail_max_size

    async def generate_thumbnail(
        self, image_data: bytes, max_size: tuple[int, int] | None = None
    ) -> ProcessingResult:
        effective_size = max_size if max_size is not None else self._thumbnail_max_size
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            get_executor(self._max_workers),
            _generate_thumbnail_sync,
            image_data,
            effective_size,
        )
        return ProcessingResult(**result)

    async def extract_metadata(self, image_data: bytes) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            get_executor(self._max_workers),
            _extract_metadata_sync,
            image_data,
        )
