"""Tests for the GetImage use case."""

from __future__ import annotations

import uuid

from src.application.use_cases.get_image import GetImageUseCase


class TestGetImageExecute:
    async def test_returns_none_when_image_not_found(self, mock_repository, mock_storage):
        mock_repository.get_by_id.return_value = None
        uc = GetImageUseCase(mock_repository, mock_storage)

        result = await uc.execute(uuid.uuid4())

        assert result is None

    async def test_returns_response_when_image_exists(
        self, sample_image_entity, mock_repository, mock_storage
    ):
        mock_repository.get_by_id.return_value = sample_image_entity
        uc = GetImageUseCase(mock_repository, mock_storage)

        result = await uc.execute(sample_image_entity.id)

        assert result is not None
        assert result.id == sample_image_entity.id
        assert result.filename == sample_image_entity.filename


class TestGetImageFile:
    async def test_get_file_returns_none_when_image_not_found(self, mock_repository, mock_storage):
        mock_repository.get_by_id.return_value = None
        uc = GetImageUseCase(mock_repository, mock_storage)

        result = await uc.get_file(uuid.uuid4())

        assert result is None

    async def test_get_file_returns_none_when_no_original_path(
        self, sample_image_entity, mock_repository, mock_storage
    ):
        sample_image_entity.original_path = None  # type: ignore[assignment]
        mock_repository.get_by_id.return_value = sample_image_entity
        uc = GetImageUseCase(mock_repository, mock_storage)

        result = await uc.get_file(sample_image_entity.id, thumbnail=False)

        assert result is None
        mock_storage.retrieve.assert_not_awaited()

    async def test_get_file_returns_none_when_no_thumbnail_path(
        self, sample_image_entity, mock_repository, mock_storage
    ):
        sample_image_entity.thumbnail_path = None
        mock_repository.get_by_id.return_value = sample_image_entity
        uc = GetImageUseCase(mock_repository, mock_storage)

        result = await uc.get_file(sample_image_entity.id, thumbnail=True)

        assert result is None
        mock_storage.retrieve.assert_not_awaited()

    async def test_get_file_returns_bytes_for_original(
        self, sample_image_entity, mock_repository, mock_storage
    ):
        mock_repository.get_by_id.return_value = sample_image_entity
        mock_storage.retrieve.return_value = b"image-bytes"
        uc = GetImageUseCase(mock_repository, mock_storage)

        result = await uc.get_file(sample_image_entity.id, thumbnail=False)

        assert result == b"image-bytes"
        mock_storage.retrieve.assert_awaited_once_with(sample_image_entity.original_path)

    async def test_get_file_returns_bytes_for_thumbnail(
        self, completed_image_entity, mock_repository, mock_storage
    ):
        mock_repository.get_by_id.return_value = completed_image_entity
        mock_storage.retrieve.return_value = b"thumb-bytes"
        uc = GetImageUseCase(mock_repository, mock_storage)

        result = await uc.get_file(completed_image_entity.id, thumbnail=True)

        assert result == b"thumb-bytes"
        mock_storage.retrieve.assert_awaited_once_with(completed_image_entity.thumbnail_path)
