"""Shared test fixtures."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from PIL import Image as PILImage

from src.domain.entities.image import Image, ImageMetadata, ProcessingStatus
from src.domain.interfaces.image_processor import ImageProcessor, ProcessingResult
from src.domain.interfaces.image_repository import ImageRepository
from src.domain.interfaces.image_storage import ImageStorage


@pytest.fixture
def sample_image_bytes() -> bytes:
    """Generate a minimal valid PNG in memory."""
    img = PILImage.new("RGB", (100, 80), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def sample_image_entity() -> Image:
    return Image(
        id=uuid.uuid4(),
        filename="test.png",
        original_path="/data/images/abc123_test.png",
        status=ProcessingStatus.PENDING,
        tags=["test"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def completed_image_entity() -> Image:
    return Image(
        id=uuid.uuid4(),
        filename="done.png",
        original_path="/data/images/def456_done.png",
        thumbnail_path="/data/images/thumb_done.png",
        metadata=ImageMetadata(width=100, height=80, format="PNG", size_bytes=1024, channels=3),
        status=ProcessingStatus.COMPLETED,
        tags=["processed"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_repository() -> ImageRepository:
    repo = AsyncMock(spec=ImageRepository)
    repo.save = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.list_images = AsyncMock(return_value=[])
    repo.delete = AsyncMock(return_value=True)
    repo.get_expired = AsyncMock(return_value=[])
    repo.delete_expired_batch = AsyncMock(return_value=[])
    repo.count = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_storage() -> ImageStorage:
    storage = AsyncMock(spec=ImageStorage)
    storage.store = AsyncMock(return_value="/data/images/abc_test.png")
    storage.retrieve = AsyncMock(return_value=b"fake-data")
    storage.delete = AsyncMock(return_value=True)
    return storage


@pytest.fixture
def mock_processor() -> ImageProcessor:
    processor = AsyncMock(spec=ImageProcessor)
    processor.generate_thumbnail = AsyncMock(
        return_value=ProcessingResult(
            thumbnail_data=b"thumb-bytes",
            width=256,
            height=200,
            format="PNG",
            size_bytes=500,
            channels=3,
        )
    )
    processor.extract_metadata = AsyncMock(
        return_value={"width": 100, "height": 80, "format": "PNG"}
    )
    return processor
