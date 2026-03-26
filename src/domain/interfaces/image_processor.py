"""Port: image processing operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProcessingResult:
    thumbnail_data: bytes
    width: int
    height: int
    format: str
    size_bytes: int
    channels: int


class ImageProcessor(ABC):
    """Abstract processor for CPU-bound image transformations."""

    @abstractmethod
    async def generate_thumbnail(
        self, image_data: bytes, max_size: tuple[int, int] = (256, 256)
    ) -> ProcessingResult: ...

    @abstractmethod
    async def extract_metadata(self, image_data: bytes) -> dict: ...
