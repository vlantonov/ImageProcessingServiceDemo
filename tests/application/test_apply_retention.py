"""Tests for the ApplyRetention use case."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.application.use_cases.apply_retention import ApplyRetentionUseCase
from src.domain.entities.image import Image, ProcessingStatus


@pytest.mark.asyncio
async def test_retention_deletes_expired(mock_repository, mock_storage):
    expired_img = Image(
        id=uuid.uuid4(),
        filename="old.png",
        original_path="/data/old.png",
        thumbnail_path="/data/thumb_old.png",
        status=ProcessingStatus.COMPLETED,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    mock_repository.get_expired.return_value = [expired_img]

    uc = ApplyRetentionUseCase(mock_repository, mock_storage)
    result = await uc.execute(batch_size=10)

    assert result.deleted_count == 1
    assert result.errors == 0
    mock_storage.delete.assert_any_await("/data/old.png")
    mock_storage.delete.assert_any_await("/data/thumb_old.png")
    mock_repository.delete.assert_awaited_once_with(expired_img.id)


@pytest.mark.asyncio
async def test_retention_no_expired(mock_repository, mock_storage):
    mock_repository.get_expired.return_value = []

    uc = ApplyRetentionUseCase(mock_repository, mock_storage)
    result = await uc.execute()

    assert result.deleted_count == 0
    assert result.errors == 0
