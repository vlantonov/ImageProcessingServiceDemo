"""Use case: upload a new image and persist its metadata."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

from src.application.dto.image_dto import ImageResponse
from src.domain.entities.image import Image
from src.domain.interfaces.image_repository import ImageRepository
from src.domain.interfaces.image_storage import ImageStorage
from src.domain.interfaces.message_broker import Message, MessageBroker

logger = logging.getLogger(__name__)

IMAGE_PROCESSING_TOPIC = "image.processing"


class UploadImageUseCase:
    def __init__(
        self,
        repository: ImageRepository,
        storage: ImageStorage,
        broker: MessageBroker | None = None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._broker = broker

    async def execute(
        self,
        filename: str,
        data: bytes,
        tags: list[str] | None = None,
        ttl_hours: int | None = None,
    ) -> ImageResponse:
        storage_path = await self._storage.store(filename, data)

        expires_at = None
        if ttl_hours is not None:
            expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)

        image = Image(
            filename=filename,
            original_path=storage_path,
            tags=tags or [],
            expires_at=expires_at,
        )

        saved = await self._repository.save(image)
        logger.info("Image persisted: id=%s filename=%s path=%s", saved.id, filename, storage_path)
        self._record_upload()

        if self._broker is not None:
            await self._broker.publish(
                Message(
                    topic=IMAGE_PROCESSING_TOPIC,
                    key=str(saved.id),
                    value=json.dumps({"image_id": str(saved.id)}).encode(),
                )
            )
            logger.info("Processing task published for image %s", saved.id)

        return _to_response(saved)

    @staticmethod
    def _record_upload() -> None:
        try:
            from src.infrastructure.observability.metrics import image_uploads_total

            image_uploads_total.add(1)
        except Exception:
            pass


def _to_response(img: Image) -> ImageResponse:
    return ImageResponse(
        id=img.id,
        filename=img.filename,
        status=img.status.value,
        width=img.metadata.width if img.metadata else None,
        height=img.metadata.height if img.metadata else None,
        format=img.metadata.format if img.metadata else None,
        size_bytes=img.metadata.size_bytes if img.metadata else None,
        tags=img.tags,
        created_at=img.created_at,
        updated_at=img.updated_at,
        expires_at=img.expires_at,
        thumbnail_available=img.thumbnail_path is not None,
    )
