"""Tests for ListImagesUseCase — pagination, status filtering, and response mapping."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from src.application.dto.image_dto import ImageListResponse
from src.application.use_cases.list_images import ListImagesUseCase
from src.domain.entities.image import Image, ImageMetadata, ProcessingStatus


def _make_image(
    *,
    status: ProcessingStatus = ProcessingStatus.PENDING,
    metadata: ImageMetadata | None = None,
    thumbnail_path: str | None = None,
) -> Image:
    return Image(
        id=uuid.uuid4(),
        filename="img.png",
        original_path="/data/img.png",
        thumbnail_path=thumbnail_path,
        metadata=metadata,
        status=status,
        tags=["tag"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class TestListImagesUseCase:
    async def test_empty_list(self, mock_repository: AsyncMock):
        use_case = ListImagesUseCase(mock_repository)

        result = await use_case.execute()

        assert isinstance(result, ImageListResponse)
        assert result.images == []
        assert result.total == 0
        assert result.offset == 0
        assert result.limit == 50
        mock_repository.list_images.assert_awaited_once_with(offset=0, limit=50, status=None)
        mock_repository.count.assert_awaited_once_with(status=None)

    async def test_returns_images_with_correct_mapping(self, mock_repository: AsyncMock):
        images = [
            _make_image(
                status=ProcessingStatus.COMPLETED,
                metadata=ImageMetadata(
                    width=800, height=600, format="PNG", size_bytes=1024, channels=3
                ),
                thumbnail_path="/data/thumb.png",
            ),
            _make_image(status=ProcessingStatus.PENDING),
        ]
        mock_repository.list_images.return_value = images
        mock_repository.count.return_value = 2
        use_case = ListImagesUseCase(mock_repository)

        result = await use_case.execute()

        assert len(result.images) == 2
        assert result.total == 2

        completed = result.images[0]
        assert completed.status == "completed"
        assert completed.width == 800
        assert completed.height == 600
        assert completed.format == "PNG"
        assert completed.size_bytes == 1024
        assert completed.thumbnail_available is True

        pending = result.images[1]
        assert pending.status == "pending"
        assert pending.width is None
        assert pending.thumbnail_available is False

    async def test_pagination_params_forwarded(self, mock_repository: AsyncMock):
        mock_repository.count.return_value = 100
        use_case = ListImagesUseCase(mock_repository)

        result = await use_case.execute(offset=10, limit=25)

        assert result.offset == 10
        assert result.limit == 25
        mock_repository.list_images.assert_awaited_once_with(offset=10, limit=25, status=None)

    async def test_status_filter_forwarded(self, mock_repository: AsyncMock):
        mock_repository.count.return_value = 5
        use_case = ListImagesUseCase(mock_repository)

        await use_case.execute(status="completed")

        mock_repository.list_images.assert_awaited_once_with(offset=0, limit=50, status="completed")
        mock_repository.count.assert_awaited_once_with(status="completed")

    async def test_total_reflects_count_not_page_size(self, mock_repository: AsyncMock):
        mock_repository.list_images.return_value = [_make_image() for _ in range(10)]
        mock_repository.count.return_value = 42
        use_case = ListImagesUseCase(mock_repository)

        result = await use_case.execute(offset=0, limit=10)

        assert len(result.images) == 10
        assert result.total == 42
