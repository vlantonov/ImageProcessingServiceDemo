"""Factory for selecting an image processor backend."""

from __future__ import annotations

from src.domain.interfaces.image_processor import ImageProcessor
from src.infrastructure.processing.pillow_processor import PillowImageProcessor


def build_image_processor(
    *,
    backend: str,
    max_workers: int,
    thumbnail_max_size: tuple[int, int],
) -> ImageProcessor:
    if backend == "pillow":
        return PillowImageProcessor(
            max_workers=max_workers,
            thumbnail_max_size=thumbnail_max_size,
        )

    if backend == "cpp":
        from src.infrastructure.processing.cpp_processor import CppImageProcessor

        try:
            return CppImageProcessor(
                max_workers=max_workers,
                thumbnail_max_size=thumbnail_max_size,
            )
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "IMG_PROCESSING_BACKEND=cpp requires the compiled fast_resize module. "
                "Build it with: cd cpp && ./build.sh"
            ) from exc

    raise ValueError(f"Unsupported IMG_PROCESSING_BACKEND value: {backend!r}")
