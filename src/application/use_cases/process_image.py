"""Use case: process an uploaded image (thumbnail + metadata extraction).

Demonstrates parallelism by offloading CPU-bound Pillow work to a
ProcessPoolExecutor via asyncio.
"""

from __future__ import annotations

import logging
import uuid

from src.domain.entities.image import ImageMetadata
from src.domain.interfaces.image_processor import ImageProcessor
from src.domain.interfaces.image_repository import ImageRepository
from src.domain.interfaces.image_storage import ImageStorage

logger = logging.getLogger(__name__)


class ProcessImageUseCase:
    def __init__(
        self,
        repository: ImageRepository,
        storage: ImageStorage,
        processor: ImageProcessor,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._processor = processor

    async def execute(self, image_id: uuid.UUID) -> bool:
        image = await self._repository.get_by_id(image_id)
        if image is None:
            return False

        image.mark_processing()
        await self._repository.save(image)

        thumb_path: str | None = None
        try:
            raw_data = await self._storage.retrieve(image.original_path)
            result = await self._processor.generate_thumbnail(raw_data)

            thumb_path = await self._storage.store(f"thumb_{image.filename}", result.thumbnail_data)

            metadata = ImageMetadata(
                width=result.width,
                height=result.height,
                format=result.format,
                size_bytes=result.size_bytes,
                channels=result.channels,
            )
            image.mark_completed(thumb_path, metadata)
            await self._repository.save(image)
        except Exception:
            logger.exception("Failed to process image %s", image_id)
            if thumb_path is not None:
                try:
                    await self._storage.delete(thumb_path)
                except Exception:
                    logger.warning("Failed to clean up thumbnail %s", thumb_path)
            image.mark_failed()
            await self._repository.save(image)
            raise

        return True
