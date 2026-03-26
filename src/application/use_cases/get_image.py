"""Use case: retrieve a single image by id."""

from __future__ import annotations

import uuid

from src.application.dto.image_dto import ImageResponse
from src.application.use_cases.upload_image import _to_response
from src.domain.interfaces.image_repository import ImageRepository
from src.domain.interfaces.image_storage import ImageStorage


class GetImageUseCase:
    def __init__(self, repository: ImageRepository, storage: ImageStorage) -> None:
        self._repository = repository
        self._storage = storage

    async def execute(self, image_id: uuid.UUID) -> ImageResponse | None:
        image = await self._repository.get_by_id(image_id)
        if image is None:
            return None
        return _to_response(image)

    async def get_file(self, image_id: uuid.UUID, thumbnail: bool = False) -> bytes | None:
        image = await self._repository.get_by_id(image_id)
        if image is None:
            return None
        path = image.thumbnail_path if thumbnail else image.original_path
        if path is None:
            return None
        return await self._storage.retrieve(path)
