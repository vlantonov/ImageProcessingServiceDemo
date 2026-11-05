"""C++-accelerated image processor via pybind11 fast_resize module."""

from __future__ import annotations

import asyncio
import importlib
import io
import sys
from pathlib import Path
from types import ModuleType

from PIL import Image as PILImage
from PIL import ImageFile

from src.domain.interfaces.image_processor import ImageProcessor, ProcessingResult
from src.infrastructure.processing.pillow_processor import (
    _extract_metadata_sync,
    get_executor,
)

ImageFile.LOAD_TRUNCATED_IMAGES = False

_fast_resize_module: ModuleType | None = None
_SUPPORTED_MODES = {"RGB", "RGBA"}


def _load_fast_resize_module() -> ModuleType:
    global _fast_resize_module
    if _fast_resize_module is not None:
        return _fast_resize_module

    search_paths = [
        Path.cwd() / "cpp" / "build",
        Path(__file__).resolve().parents[3] / "cpp" / "build",
        Path(__file__).resolve().parents[3] / "src",
    ]

    for candidate in search_paths:
        if candidate.exists():
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)

    _fast_resize_module = importlib.import_module("fast_resize")
    return _fast_resize_module


def _normalize_mode(img: PILImage.Image) -> PILImage.Image:
    if img.mode in _SUPPORTED_MODES:
        return img
    if "A" in img.getbands():
        return img.convert("RGBA")
    return img.convert("RGB")


def _generate_thumbnail_cpp_sync(data: bytes, max_size: tuple[int, int]) -> dict:
    module = _load_fast_resize_module()
    img: PILImage.Image = PILImage.open(io.BytesIO(data))
    out_format = img.format or "PNG"
    img = _normalize_mode(img)

    src_w, src_h = img.size
    dst_w, dst_h = module.fit_dimensions(src_w, src_h, max_size[0], max_size[1])
    if (dst_w, dst_h) == (src_w, src_h):
        resized: PILImage.Image = img
    else:
        raw = img.tobytes()
        channels = len(img.getbands())
        resized_raw = module.bilinear_resize_bytes(raw, src_w, src_h, channels, dst_w, dst_h)
        resized = PILImage.frombytes(img.mode, (dst_w, dst_h), resized_raw)

    output = io.BytesIO()
    resized.save(output, format=out_format)

    channels = len(resized.getbands())
    return {
        "thumbnail_data": output.getvalue(),
        "width": resized.width,
        "height": resized.height,
        "format": out_format,
        "size_bytes": len(data),
        "channels": channels,
    }


class CppImageProcessor(ImageProcessor):
    def __init__(
        self, max_workers: int = 4, thumbnail_max_size: tuple[int, int] = (256, 256)
    ) -> None:
        self._max_workers = max_workers
        self._thumbnail_max_size = thumbnail_max_size
        _load_fast_resize_module()

    async def generate_thumbnail(
        self, image_data: bytes, max_size: tuple[int, int] | None = None
    ) -> ProcessingResult:
        effective_size = max_size if max_size is not None else self._thumbnail_max_size
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            get_executor(self._max_workers),
            _generate_thumbnail_cpp_sync,
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
