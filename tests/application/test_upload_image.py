"""Tests for the UploadImage use case."""

from __future__ import annotations

import pytest

from src.application.use_cases.upload_image import UploadImageUseCase
from src.domain.entities.image import ProcessingStatus


@pytest.mark.asyncio
async def test_upload_stores_and_persists(mock_repository, mock_storage):
    mock_repository.save.side_effect = lambda img: img  # return the same entity
    uc = UploadImageUseCase(mock_repository, mock_storage)

    result = await uc.execute(filename="cat.png", data=b"image-data", tags=["cat"])

    mock_storage.store.assert_awaited_once_with("cat.png", b"image-data")
    mock_repository.save.assert_awaited_once()
    assert result.filename == "cat.png"
    assert result.status == ProcessingStatus.PENDING.value
    assert result.tags == ["cat"]


@pytest.mark.asyncio
async def test_upload_with_ttl(mock_repository, mock_storage):
    mock_repository.save.side_effect = lambda img: img
    uc = UploadImageUseCase(mock_repository, mock_storage)

    result = await uc.execute(filename="tmp.png", data=b"data", ttl_hours=24)

    assert result.expires_at is not None
