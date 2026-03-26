"""Tests for the ProcessImage use case."""

from __future__ import annotations

import pytest

from src.application.use_cases.process_image import ProcessImageUseCase
from src.domain.entities.image import Image, ProcessingStatus


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
    import uuid

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
