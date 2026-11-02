"""Tests for image processor backend factory."""

from __future__ import annotations

import pytest

from src.infrastructure.processing.factory import build_image_processor
from src.infrastructure.processing.pillow_processor import PillowImageProcessor


def test_build_pillow_processor():
    processor = build_image_processor(
        backend="pillow",
        max_workers=2,
        thumbnail_max_size=(256, 256),
    )
    assert isinstance(processor, PillowImageProcessor)


def test_build_cpp_processor_missing_module(monkeypatch):
    monkeypatch.setattr(
        "src.infrastructure.processing.cpp_processor.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError("fast_resize")),
    )

    with pytest.raises(RuntimeError, match="IMG_PROCESSING_BACKEND=cpp"):
        build_image_processor(
            backend="cpp",
            max_workers=2,
            thumbnail_max_size=(256, 256),
        )


def test_build_processor_invalid_backend():
    with pytest.raises(ValueError, match="Unsupported IMG_PROCESSING_BACKEND"):
        build_image_processor(
            backend="unknown",
            max_workers=2,
            thumbnail_max_size=(256, 256),
        )
