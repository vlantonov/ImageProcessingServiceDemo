"""Use case: apply retention policies — delete expired images.

Designed to run on a schedule (e.g., Kubernetes CronJob or background task).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.domain.interfaces.image_repository import ImageRepository
from src.domain.interfaces.image_storage import ImageStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetentionResult:
    deleted_count: int
    errors: int


class ApplyRetentionUseCase:
    def __init__(self, repository: ImageRepository, storage: ImageStorage) -> None:
        self._repository = repository
        self._storage = storage

    async def execute(self, batch_size: int = 100) -> RetentionResult:
        deleted_images = await self._repository.delete_expired_batch(
            batch_size=batch_size,
        )
        errors = 0

        for image in deleted_images:
            try:
                await self._storage.delete(image.original_path)
                if image.thumbnail_path:
                    await self._storage.delete(image.thumbnail_path)
            except Exception:
                logger.exception("Failed to clean up storage for expired image %s", image.id)
                errors += 1

        logger.info("Retention sweep: deleted=%d errors=%d", len(deleted_images), errors)
        return RetentionResult(deleted_count=len(deleted_images), errors=errors)
