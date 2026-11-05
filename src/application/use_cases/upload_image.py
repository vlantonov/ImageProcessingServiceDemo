"""Use case: upload a new image and persist its metadata."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta

from src.application.dto.image_dto import ImageResponse
from src.application.use_cases.idempotency import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
)
from src.domain.entities.image import Image
from src.domain.interfaces.image_repository import ImageRepository
from src.domain.interfaces.image_storage import ImageStorage
from src.domain.interfaces.message_broker import Message, MessageBroker

logger = logging.getLogger(__name__)

IMAGE_PROCESSING_TOPIC = "image.processing"
UPLOAD_SCOPE = "upload"


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
        idempotency_key: str | None = None,
    ) -> ImageResponse:
        normalized_tags = tags or []
        request_hash = _hash_upload_request(
            filename=filename,
            data=data,
            tags=normalized_tags,
            ttl_hours=ttl_hours,
        )
        if idempotency_key is not None:
            replay = await self._load_idempotent_replay(
                key=idempotency_key, request_hash=request_hash
            )
            if replay is not None:
                return replay
            claimed = await self._repository.create_idempotency_record(
                scope=UPLOAD_SCOPE,
                key=idempotency_key,
                request_hash=request_hash,
            )
            if not claimed:
                replay = await self._load_idempotent_replay(
                    key=idempotency_key, request_hash=request_hash
                )
                if replay is not None:
                    return replay
                raise IdempotencyInProgressError("Upload with this Idempotency-Key is in progress")

        try:
            storage_path = await self._storage.store(filename, data)

            expires_at = None
            if ttl_hours is not None:
                expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)

            image = Image(
                filename=filename,
                original_path=storage_path,
                tags=normalized_tags,
                expires_at=expires_at,
            )

            saved = await self._repository.save(image)
            logger.info(
                "Image persisted: id=%s filename=%s path=%s", saved.id, filename, storage_path
            )
            self._record_upload()

            if self._broker is not None:
                try:
                    await self._broker.publish(
                        Message(
                            topic=IMAGE_PROCESSING_TOPIC,
                            key=str(saved.id),
                            value=json.dumps({"image_id": str(saved.id)}).encode(),
                        )
                    )
                    self._record_publish(IMAGE_PROCESSING_TOPIC)
                    logger.info("Processing task published for image %s", saved.id)
                except Exception:
                    self._record_publish_error(IMAGE_PROCESSING_TOPIC)
                    logger.exception("Failed to publish processing task for image %s", saved.id)

            if idempotency_key is not None:
                await self._repository.complete_idempotency_record(
                    scope=UPLOAD_SCOPE,
                    key=idempotency_key,
                    image_id=saved.id,
                )
            return _to_response(saved)
        except Exception:
            if idempotency_key is not None:
                await self._repository.delete_idempotency_record(
                    scope=UPLOAD_SCOPE,
                    key=idempotency_key,
                )
            raise

    async def _load_idempotent_replay(self, *, key: str, request_hash: str) -> ImageResponse | None:
        record = await self._repository.get_idempotency_record(scope=UPLOAD_SCOPE, key=key)
        if record is None:
            return None
        if record.request_hash != request_hash:
            raise IdempotencyConflictError(
                "Idempotency-Key reuse with a different upload payload is not allowed"
            )
        if record.status == "in_progress":
            raise IdempotencyInProgressError("Upload with this Idempotency-Key is in progress")
        if record.image_id is None:
            raise IdempotencyConflictError(
                "Completed upload idempotency record does not reference an image"
            )
        image = await self._repository.get_by_id(record.image_id)
        if image is None:
            raise IdempotencyConflictError("Idempotency replay image no longer exists")
        return _to_response(image)

    @staticmethod
    def _record_upload() -> None:
        try:
            from src.infrastructure.observability.metrics import image_uploads_total

            image_uploads_total.add(1)
        except Exception:
            pass

    @staticmethod
    def _record_publish(topic: str) -> None:
        try:
            from src.infrastructure.observability.metrics import broker_messages_published

            broker_messages_published.add(1, {"topic": topic})
        except Exception:
            pass

    @staticmethod
    def _record_publish_error(topic: str) -> None:
        try:
            from src.infrastructure.observability.metrics import broker_publish_errors

            broker_publish_errors.add(1, {"topic": topic})
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


def _hash_upload_request(
    *,
    filename: str,
    data: bytes,
    tags: list[str],
    ttl_hours: int | None,
) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    payload = json.dumps(
        {
            "filename": filename,
            "tags": tags,
            "ttl_hours": ttl_hours,
            "content_sha256": digest.hexdigest(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()
