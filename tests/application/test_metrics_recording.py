"""Tests for upload_image and process_image metrics recording paths."""

from __future__ import annotations

from unittest.mock import patch

from src.application.use_cases.process_image import ProcessImageUseCase
from src.application.use_cases.upload_image import UploadImageUseCase


class TestUploadImageMetrics:
    async def test_record_upload_succeeds(self, mock_repository, mock_storage):
        mock_repository.save.side_effect = lambda img: img
        uc = UploadImageUseCase(mock_repository, mock_storage)

        with patch(
            "src.application.use_cases.upload_image.UploadImageUseCase._record_upload"
        ) as mock_record:
            await uc.execute(filename="cat.png", data=b"image-data")
            mock_record.assert_called_once()

    async def test_record_upload_import_success(self):
        """_record_upload calls metrics.image_uploads_total.add(1)."""
        with patch("src.infrastructure.observability.metrics.image_uploads_total") as mock_counter:
            UploadImageUseCase._record_upload()
            mock_counter.add.assert_called_once_with(1)

    async def test_record_upload_swallows_import_error(self):
        """_record_upload silently catches exceptions (e.g., missing OTel deps)."""
        with patch(
            "src.infrastructure.observability.metrics.image_uploads_total",
            side_effect=RuntimeError("no OTel"),
        ):
            # Should not raise
            UploadImageUseCase._record_upload()


class TestProcessImageMetrics:
    async def test_record_duration_succeeds(self):
        with patch(
            "src.infrastructure.observability.metrics.image_processing_duration"
        ) as mock_hist:
            ProcessImageUseCase._record_duration(1.23)
            mock_hist.record.assert_called_once_with(1.23, {"operation": "thumbnail"})

    async def test_record_duration_swallows_import_error(self):
        with patch(
            "src.infrastructure.observability.metrics.image_processing_duration",
            side_effect=RuntimeError("no OTel"),
        ):
            # Should not raise
            ProcessImageUseCase._record_duration(1.0)
