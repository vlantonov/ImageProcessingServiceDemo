"""Use case: upload a new image and persist its metadata."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.application.dto.image_dto import ImageResponse
from src.domain.entities.image import Image
from src.domain.interfaces.image_repository import ImageRepository
from src.domain.interfaces.image_storage import ImageStorage


class UploadImageUseCase:
    def __init__(self, repository: ImageRepository, storage: ImageStorage) -> None:
        self._repository = repository
        self._storage = storage

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
        return _to_response(saved)


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
