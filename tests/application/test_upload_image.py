"""Tests for the UploadImage use case."""

from __future__ import annotations

import pytest

from src.application.use_cases.idempotency import IdempotencyConflictError
from src.application.use_cases.upload_image import UploadImageUseCase, _hash_upload_request
from src.domain.entities.image import ProcessingStatus
from src.domain.interfaces.image_repository import IdempotencyRecord


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


@pytest.mark.asyncio
async def test_upload_idempotency_replay_returns_existing_without_new_write(
    sample_image_entity, mock_repository, mock_storage
):
    request_hash = _hash_upload_request(
        filename=sample_image_entity.filename,
        data=b"image-data",
        tags=sample_image_entity.tags,
        ttl_hours=None,
    )
    mock_repository.get_idempotency_record.return_value = IdempotencyRecord(
        scope="upload",
        key="k1",
        request_hash=request_hash,
        status="completed",
        image_id=sample_image_entity.id,
    )
    mock_repository.get_by_id.return_value = sample_image_entity

    uc = UploadImageUseCase(mock_repository, mock_storage)
    result = await uc.execute(
        filename=sample_image_entity.filename,
        data=b"image-data",
        tags=sample_image_entity.tags,
        idempotency_key="k1",
    )

    assert result.id == sample_image_entity.id
    mock_storage.store.assert_not_called()
    mock_repository.save.assert_not_called()


@pytest.mark.asyncio
async def test_upload_idempotency_hash_conflict_raises(mock_repository, mock_storage):
    mock_repository.get_idempotency_record.return_value = IdempotencyRecord(
        scope="upload",
        key="k1",
        request_hash="different-hash",
        status="completed",
        image_id=None,
    )

    uc = UploadImageUseCase(mock_repository, mock_storage)

    with pytest.raises(IdempotencyConflictError):
        await uc.execute(filename="cat.png", data=b"image-data", idempotency_key="k1")
