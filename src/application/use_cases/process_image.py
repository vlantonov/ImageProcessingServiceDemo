"""Use case: process an uploaded image (thumbnail + metadata extraction).

Demonstrates parallelism by offloading CPU-bound Pillow work to a
ProcessPoolExecutor via asyncio.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid

from src.application.use_cases.idempotency import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
)
from src.domain.entities.image import ImageMetadata
from src.domain.interfaces.image_processor import ImageProcessor
from src.domain.interfaces.image_repository import ImageRepository
from src.domain.interfaces.image_storage import ImageStorage

logger = logging.getLogger(__name__)
PROCESS_SCOPE = "process-image"


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

    async def execute(self, image_id: uuid.UUID, idempotency_key: str | None = None) -> bool:
        request_hash = _hash_process_request(image_id)
        if idempotency_key is not None:
            replay = await self._load_idempotent_replay(
                key=idempotency_key,
                request_hash=request_hash,
            )
            if replay is not None:
                return replay
            claimed = await self._repository.create_idempotency_record(
                scope=PROCESS_SCOPE,
                key=idempotency_key,
                request_hash=request_hash,
                image_id=image_id,
            )
            if not claimed:
                replay = await self._load_idempotent_replay(
                    key=idempotency_key,
                    request_hash=request_hash,
                )
                if replay is not None:
                    return replay
                raise IdempotencyInProgressError(
                    "Processing with this Idempotency-Key is already in progress"
                )

        image = await self._repository.get_by_id(image_id)
        if image is None:
            logger.warning("Process requested for non-existent image: %s", image_id)
            if idempotency_key is not None:
                await self._repository.delete_idempotency_record(
                    scope=PROCESS_SCOPE, key=idempotency_key
                )
            return False

        start = time.perf_counter()
        thumb_path: str | None = None
        try:
            logger.info("Processing started: image=%s filename=%s", image_id, image.filename)
            image.mark_processing()
            await self._repository.save(image)

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

            elapsed = time.perf_counter() - start
            self._record_duration(elapsed)

            logger.info(
                "Processing completed: image=%s width=%d height=%d format=%s",
                image_id,
                result.width,
                result.height,
                result.format,
            )
        except Exception as e:
            logger.exception("Failed to process image %s: %s", image_id, e)
            if thumb_path is not None:
                try:
                    await self._storage.delete(thumb_path)
                except OSError:
                    logger.warning("Failed to clean up thumbnail %s", thumb_path)
            image.mark_failed()
            await self._repository.save(image)
            if idempotency_key is not None:
                await self._repository.delete_idempotency_record(
                    scope=PROCESS_SCOPE, key=idempotency_key
                )
            raise

        if idempotency_key is not None:
            await self._repository.complete_idempotency_record(
                scope=PROCESS_SCOPE,
                key=idempotency_key,
                image_id=image_id,
            )
        return True

    async def _load_idempotent_replay(self, *, key: str, request_hash: str) -> bool | None:
        record = await self._repository.get_idempotency_record(scope=PROCESS_SCOPE, key=key)
        if record is None:
            return None
        if record.request_hash != request_hash:
            raise IdempotencyConflictError(
                "Idempotency-Key reuse with a different image_id is not allowed"
            )
        if record.status == "in_progress":
            raise IdempotencyInProgressError(
                "Processing with this Idempotency-Key is already in progress"
            )
        return True

    @staticmethod
    def _record_duration(elapsed: float) -> None:
        try:
            from src.infrastructure.observability.metrics import image_processing_duration

            image_processing_duration.record(elapsed, {"operation": "thumbnail"})
        except Exception:
            pass


def _hash_process_request(image_id: uuid.UUID) -> str:
    payload = f"image_id:{image_id}".encode()
    return hashlib.sha256(payload).hexdigest()
