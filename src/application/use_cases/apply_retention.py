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
        expired = await self._repository.get_expired(batch_size=batch_size)
        deleted = 0
        errors = 0

        for image in expired:
            try:
                await self._storage.delete(image.original_path)
                if image.thumbnail_path:
                    await self._storage.delete(image.thumbnail_path)
                await self._repository.delete(image.id)
                deleted += 1
            except Exception:
                logger.exception("Failed to delete expired image %s", image.id)
                errors += 1

        logger.info("Retention sweep: deleted=%d errors=%d", deleted, errors)
        return RetentionResult(deleted_count=deleted, errors=errors)
