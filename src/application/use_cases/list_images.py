"""Use case: list images with pagination and optional filtering."""

from __future__ import annotations

from src.application.dto.image_dto import ImageListResponse
from src.application.use_cases.upload_image import _to_response
from src.domain.interfaces.image_repository import ImageRepository


class ListImagesUseCase:
    def __init__(self, repository: ImageRepository) -> None:
        self._repository = repository

    async def execute(
        self, *, offset: int = 0, limit: int = 50, status: str | None = None
    ) -> ImageListResponse:
        images = await self._repository.list_images(offset=offset, limit=limit, status=status)
        total = await self._repository.count(status=status)
        return ImageListResponse(
            images=[_to_response(img) for img in images],
            total=total,
            offset=offset,
            limit=limit,
        )
