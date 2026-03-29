"""Tests for the ProcessImage use case."""

from __future__ import annotations

import uuid

import pytest

from src.application.use_cases.process_image import ProcessImageUseCase
from src.domain.entities.image import ProcessingStatus


@pytest.mark.asyncio
async def test_process_image_success(
    sample_image_entity, mock_repository, mock_storage, mock_processor
):
    entity = sample_image_entity
    mock_repository.get_by_id.return_value = entity
    mock_repository.save.side_effect = lambda img: img
    mock_storage.retrieve.return_value = b"raw-pixels"

    uc = ProcessImageUseCase(mock_repository, mock_storage, mock_processor)
    ok = await uc.execute(entity.id)

    assert ok is True
    assert entity.status == ProcessingStatus.COMPLETED
    assert entity.thumbnail_path is not None
    assert entity.metadata is not None
    mock_processor.generate_thumbnail.assert_awaited_once_with(b"raw-pixels")


@pytest.mark.asyncio
async def test_process_image_not_found(mock_repository, mock_storage, mock_processor):

    mock_repository.get_by_id.return_value = None
    uc = ProcessImageUseCase(mock_repository, mock_storage, mock_processor)
    ok = await uc.execute(uuid.uuid4())

    assert ok is False


@pytest.mark.asyncio
async def test_process_image_marks_failed_on_error(
    sample_image_entity, mock_repository, mock_storage, mock_processor
):
    entity = sample_image_entity
    mock_repository.get_by_id.return_value = entity
    mock_repository.save.side_effect = lambda img: img
    mock_storage.retrieve.side_effect = FileNotFoundError("gone")

    uc = ProcessImageUseCase(mock_repository, mock_storage, mock_processor)

    with pytest.raises(FileNotFoundError):
        await uc.execute(entity.id)

    assert entity.status == ProcessingStatus.FAILED


@pytest.mark.asyncio
async def test_process_image_cleans_up_thumbnail_on_save_failure(
    sample_image_entity, mock_repository, mock_storage, mock_processor
):
    """If repository.save fails after thumbnail is stored, the thumbnail must be deleted."""
    entity = sample_image_entity
    mock_repository.get_by_id.return_value = entity

    call_count = 0

    async def _save_side_effect(img):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return img  # mark_processing save succeeds
        if call_count == 2:
            raise RuntimeError("DB write failed")  # mark_completed save fails
        return img  # mark_failed save succeeds

    mock_repository.save.side_effect = _save_side_effect
    mock_storage.retrieve.return_value = b"raw-pixels"
    mock_storage.store.return_value = "/data/images/thumb_test.png"

    uc = ProcessImageUseCase(mock_repository, mock_storage, mock_processor)

    with pytest.raises(RuntimeError, match="DB write failed"):
        await uc.execute(entity.id)

    assert entity.status == ProcessingStatus.FAILED
    mock_storage.delete.assert_awaited_once_with("/data/images/thumb_test.png")
