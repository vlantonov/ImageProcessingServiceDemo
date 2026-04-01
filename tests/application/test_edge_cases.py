"""Edge-case tests: failures, timeouts, and concurrent access in use cases."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.application.use_cases.apply_retention import ApplyRetentionUseCase
from src.application.use_cases.get_image import GetImageUseCase
from src.application.use_cases.process_image import ProcessImageUseCase
from src.application.use_cases.upload_image import UploadImageUseCase
from src.domain.entities.image import Image, ProcessingStatus
from src.infrastructure.processing.pipeline import process_batch

# ── ProcessImage failure edge cases ──────────────────────────────────────────


class TestProcessImageFailures:
    async def test_thumbnail_cleanup_failure_still_marks_failed(
        self, sample_image_entity, mock_repository, mock_storage, mock_processor
    ):
        """When thumbnail cleanup itself fails (OSError), image should still be marked FAILED."""
        entity = sample_image_entity
        mock_repository.get_by_id.return_value = entity

        call_count = 0

        async def _save_side_effect(img):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("DB write failed")
            return img

        mock_repository.save.side_effect = _save_side_effect
        mock_storage.retrieve.return_value = b"raw-pixels"
        mock_storage.store.return_value = "/data/images/thumb_test.png"
        mock_storage.delete.side_effect = OSError("disk full")

        uc = ProcessImageUseCase(mock_repository, mock_storage, mock_processor)

        with pytest.raises(RuntimeError, match="DB write failed"):
            await uc.execute(entity.id)

        assert entity.status == ProcessingStatus.FAILED

    async def test_processor_raises_value_error(
        self, sample_image_entity, mock_repository, mock_storage, mock_processor
    ):
        """Processor raising ValueError (e.g., corrupt data) should mark FAILED and re-raise."""
        entity = sample_image_entity
        mock_repository.get_by_id.return_value = entity
        mock_repository.save.side_effect = lambda img: img
        mock_storage.retrieve.return_value = b"corrupted"
        mock_processor.generate_thumbnail.side_effect = ValueError("Cannot identify image file")

        uc = ProcessImageUseCase(mock_repository, mock_storage, mock_processor)

        with pytest.raises(ValueError, match="Cannot identify"):
            await uc.execute(entity.id)

        assert entity.status == ProcessingStatus.FAILED

    async def test_storage_retrieve_permission_error(
        self, sample_image_entity, mock_repository, mock_storage, mock_processor
    ):
        """PermissionError on retrieve should mark FAILED."""
        entity = sample_image_entity
        mock_repository.get_by_id.return_value = entity
        mock_repository.save.side_effect = lambda img: img
        mock_storage.retrieve.side_effect = PermissionError("Access denied")

        uc = ProcessImageUseCase(mock_repository, mock_storage, mock_processor)

        with pytest.raises(PermissionError):
            await uc.execute(entity.id)

        assert entity.status == ProcessingStatus.FAILED

    async def test_thumbnail_store_fails_no_cleanup_needed(
        self, sample_image_entity, mock_repository, mock_storage, mock_processor
    ):
        """If storage.store for thumbnail fails, no thumbnail to clean up."""
        entity = sample_image_entity
        mock_repository.get_by_id.return_value = entity
        mock_repository.save.side_effect = lambda img: img
        mock_storage.retrieve.return_value = b"raw-pixels"
        mock_storage.store.side_effect = OSError("Disk full")

        uc = ProcessImageUseCase(mock_repository, mock_storage, mock_processor)

        with pytest.raises(OSError, match="Disk full"):
            await uc.execute(entity.id)

        assert entity.status == ProcessingStatus.FAILED
        # storage.delete should not be called since store never returned a path
        mock_storage.delete.assert_not_awaited()

    async def test_mark_processing_save_fails(
        self, sample_image_entity, mock_repository, mock_storage, mock_processor
    ):
        """If the first save (mark_processing) fails, processing should not proceed."""
        entity = sample_image_entity
        mock_repository.get_by_id.return_value = entity
        mock_repository.save.side_effect = RuntimeError("DB unavailable")

        uc = ProcessImageUseCase(mock_repository, mock_storage, mock_processor)

        with pytest.raises(RuntimeError, match="DB unavailable"):
            await uc.execute(entity.id)

        # Processor should never be called
        mock_processor.generate_thumbnail.assert_not_awaited()

    async def test_mark_failed_save_also_raises(
        self, sample_image_entity, mock_repository, mock_storage, mock_processor
    ):
        """If saving FAILED status also fails, the original error still propagates."""
        entity = sample_image_entity
        mock_repository.get_by_id.return_value = entity

        call_count = 0

        async def _save_side_effect(img):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return img  # mark_processing succeeds
            raise RuntimeError(f"DB error #{call_count}")

        mock_repository.save.side_effect = _save_side_effect
        mock_storage.retrieve.return_value = b"raw-pixels"

        uc = ProcessImageUseCase(mock_repository, mock_storage, mock_processor)

        with pytest.raises(RuntimeError):
            await uc.execute(entity.id)


# ── UploadImage failure edge cases ───────────────────────────────────────────


class TestUploadImageFailures:
    async def test_storage_failure_propagates(self, mock_repository, mock_storage):
        """If storage.store raises, the error propagates (no partial DB record)."""
        mock_storage.store.side_effect = OSError("No space left on device")

        uc = UploadImageUseCase(mock_repository, mock_storage)

        with pytest.raises(OSError, match="No space left"):
            await uc.execute(filename="test.png", data=b"data")

        mock_repository.save.assert_not_awaited()

    async def test_repository_failure_after_storage(self, mock_repository, mock_storage):
        """If repository.save fails after storage succeeds, error propagates."""
        mock_storage.store.return_value = "/data/images/abc_test.png"
        mock_repository.save.side_effect = RuntimeError("DB connection lost")

        uc = UploadImageUseCase(mock_repository, mock_storage)

        with pytest.raises(RuntimeError, match="DB connection lost"):
            await uc.execute(filename="test.png", data=b"data")

    async def test_upload_empty_filename(self, mock_repository, mock_storage):
        """Upload with empty filename should still work (uses default)."""
        mock_repository.save.side_effect = lambda img: img
        uc = UploadImageUseCase(mock_repository, mock_storage)

        result = await uc.execute(filename="", data=b"data")

        assert result.filename == ""

    async def test_upload_with_no_tags_defaults_empty_list(self, mock_repository, mock_storage):
        """Tags=None gets normalized to empty list."""
        mock_repository.save.side_effect = lambda img: img
        uc = UploadImageUseCase(mock_repository, mock_storage)

        result = await uc.execute(filename="test.png", data=b"data", tags=None)

        assert result.tags == []


# ── ApplyRetention failure edge cases ────────────────────────────────────────


class TestApplyRetentionFailures:
    async def test_partial_storage_cleanup_failure(self, mock_repository, mock_storage):
        """If some storage deletes fail, counts errors without halting."""
        images = [
            Image(
                id=uuid.uuid4(),
                filename=f"img{i}.png",
                original_path=f"/data/img{i}.png",
                thumbnail_path=f"/data/thumb{i}.png" if i % 2 == 0 else None,
                status=ProcessingStatus.COMPLETED,
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )
            for i in range(4)
        ]
        mock_repository.delete_expired_batch.return_value = images

        call_count = 0

        async def _delete_side_effect(path):
            nonlocal call_count
            call_count += 1
            if "img1" in path:
                raise OSError("Permission denied")
            return True

        mock_storage.delete.side_effect = _delete_side_effect

        uc = ApplyRetentionUseCase(mock_repository, mock_storage)
        result = await uc.execute()

        assert result.deleted_count == 4
        assert result.errors == 1  # Only img1 original fails

    async def test_thumbnail_delete_failure_counted_as_error(self, mock_repository, mock_storage):
        """Thumbnail delete failure should count as an error for that image."""
        image = Image(
            id=uuid.uuid4(),
            filename="old.png",
            original_path="/data/old.png",
            thumbnail_path="/data/thumb_old.png",
            status=ProcessingStatus.COMPLETED,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        mock_repository.delete_expired_batch.return_value = [image]

        async def _delete_side_effect(path):
            if "thumb" in path:
                raise OSError("Cannot delete thumbnail")
            return True

        mock_storage.delete.side_effect = _delete_side_effect

        uc = ApplyRetentionUseCase(mock_repository, mock_storage)
        result = await uc.execute()

        assert result.deleted_count == 1
        assert result.errors == 1

    async def test_repository_delete_expired_batch_propagates(self, mock_repository, mock_storage):
        """If the DB batch delete itself fails, the error propagates."""
        mock_repository.delete_expired_batch.side_effect = RuntimeError("DB deadlock")

        uc = ApplyRetentionUseCase(mock_repository, mock_storage)

        with pytest.raises(RuntimeError, match="DB deadlock"):
            await uc.execute()

    async def test_retention_with_no_thumbnail_path(self, mock_repository, mock_storage):
        """Images without thumbnails should only delete original."""
        image = Image(
            id=uuid.uuid4(),
            filename="nothumbnail.png",
            original_path="/data/nothumbnail.png",
            thumbnail_path=None,
            status=ProcessingStatus.PENDING,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        mock_repository.delete_expired_batch.return_value = [image]

        uc = ApplyRetentionUseCase(mock_repository, mock_storage)
        result = await uc.execute()

        assert result.deleted_count == 1
        assert result.errors == 0
        mock_storage.delete.assert_awaited_once_with("/data/nothumbnail.png")


# ── GetImage failure edge cases ──────────────────────────────────────────────


class TestGetImageFailures:
    async def test_get_file_storage_error(self, mock_repository, mock_storage):
        """If storage.retrieve raises, it propagates."""
        entity = Image(
            id=uuid.uuid4(),
            filename="test.png",
            original_path="/data/test.png",
            status=ProcessingStatus.COMPLETED,
        )
        mock_repository.get_by_id.return_value = entity
        mock_storage.retrieve.side_effect = FileNotFoundError("File missing")

        uc = GetImageUseCase(mock_repository, mock_storage)

        with pytest.raises(FileNotFoundError):
            await uc.get_file(entity.id)

    async def test_get_file_thumbnail_when_no_thumbnail_path(self, mock_repository, mock_storage):
        """Requesting thumbnail when no thumbnail_path returns None."""
        entity = Image(
            id=uuid.uuid4(),
            filename="test.png",
            original_path="/data/test.png",
            thumbnail_path=None,
            status=ProcessingStatus.PENDING,
        )
        mock_repository.get_by_id.return_value = entity

        uc = GetImageUseCase(mock_repository, mock_storage)
        result = await uc.get_file(entity.id, thumbnail=True)

        assert result is None
        mock_storage.retrieve.assert_not_awaited()

    async def test_get_file_not_found_returns_none(self, mock_repository, mock_storage):
        """Image not in repository returns None."""
        mock_repository.get_by_id.return_value = None

        uc = GetImageUseCase(mock_repository, mock_storage)
        result = await uc.get_file(uuid.uuid4())

        assert result is None


# ── Timeout edge cases ───────────────────────────────────────────────────────


class TestTimeouts:
    async def test_process_image_timeout(
        self, sample_image_entity, mock_repository, mock_storage, mock_processor
    ):
        """Processing that exceeds a timeout should raise TimeoutError."""
        entity = sample_image_entity
        mock_repository.get_by_id.return_value = entity
        mock_repository.save.side_effect = lambda img: img
        mock_storage.retrieve.return_value = b"raw-pixels"

        async def _slow_thumbnail(*args, **kwargs):
            await asyncio.sleep(10)

        mock_processor.generate_thumbnail.side_effect = _slow_thumbnail

        uc = ProcessImageUseCase(mock_repository, mock_storage, mock_processor)

        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.05):
                await uc.execute(entity.id)

    async def test_upload_storage_timeout(self, mock_repository, mock_storage):
        """Storage that times out should propagate the error."""

        async def _slow_store(*args, **kwargs):
            await asyncio.sleep(10)

        mock_storage.store.side_effect = _slow_store

        uc = UploadImageUseCase(mock_repository, mock_storage)

        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.05):
                await uc.execute(filename="test.png", data=b"data")

    async def test_retention_timeout(self, mock_repository, mock_storage):
        """Retention sweep that times out should propagate."""

        async def _slow_batch(*args, **kwargs):
            await asyncio.sleep(10)
            return []

        mock_repository.delete_expired_batch.side_effect = _slow_batch

        uc = ApplyRetentionUseCase(mock_repository, mock_storage)

        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.05):
                await uc.execute()


# ── Concurrent access / pipeline edge cases ──────────────────────────────────


class TestConcurrentAccess:
    async def test_pipeline_mixed_results(self, mock_repository, mock_storage, mock_processor):
        """Pipeline with mix of success, not-found, and exceptions."""
        entities = {
            uuid.uuid4(): "success",
            uuid.uuid4(): "not_found",
            uuid.uuid4(): "error",
        }
        ids = list(entities.keys())

        async def _get_by_id(image_id):
            action = entities[image_id]
            if action == "not_found":
                return None
            return Image(
                id=image_id,
                filename="test.png",
                original_path="/data/test.png",
                status=ProcessingStatus.PENDING,
            )

        async def _retrieve(path):
            return b"raw-pixels"

        call_count = {}

        async def _save(img):
            call_count.setdefault(img.id, 0)
            call_count[img.id] += 1
            action = entities[img.id]
            if action == "error" and call_count[img.id] == 1:
                return img  # mark_processing succeeds
            if action == "error" and call_count[img.id] == 2:
                raise RuntimeError("DB error")
            return img

        mock_repository.get_by_id.side_effect = _get_by_id
        mock_repository.save.side_effect = _save
        mock_storage.retrieve.side_effect = _retrieve

        uc = ProcessImageUseCase(mock_repository, mock_storage, mock_processor)
        result = await process_batch(uc, ids, concurrency=2)

        assert result["success"] == 1
        assert result["failed"] == 2  # not_found + error

    async def test_pipeline_all_failures(self, mock_repository, mock_storage, mock_processor):
        """Pipeline where every task fails."""
        ids = [uuid.uuid4() for _ in range(5)]
        mock_repository.get_by_id.return_value = None

        uc = ProcessImageUseCase(mock_repository, mock_storage, mock_processor)
        result = await process_batch(uc, ids, concurrency=3)

        assert result["success"] == 0
        assert result["failed"] == 5

    async def test_pipeline_empty_batch(self, mock_repository, mock_storage, mock_processor):
        """Empty batch should return zero counts."""
        uc = ProcessImageUseCase(mock_repository, mock_storage, mock_processor)
        result = await process_batch(uc, [], concurrency=4)

        assert result["success"] == 0
        assert result["failed"] == 0

    async def test_pipeline_concurrency_one(self, mock_repository, mock_storage, mock_processor):
        """Concurrency=1 should serialize processing."""
        ids = [uuid.uuid4() for _ in range(3)]
        mock_repository.get_by_id.return_value = None

        uc = ProcessImageUseCase(mock_repository, mock_storage, mock_processor)
        result = await process_batch(uc, ids, concurrency=1)

        assert result["failed"] == 3

    async def test_concurrent_uploads(self, mock_repository, mock_storage):
        """Multiple concurrent uploads should all succeed independently."""
        mock_repository.save.side_effect = lambda img: img
        upload_count = 0

        async def _store(filename, data):
            nonlocal upload_count
            upload_count += 1
            return f"/data/{upload_count}_{filename}"

        mock_storage.store.side_effect = _store

        uc = UploadImageUseCase(mock_repository, mock_storage)
        tasks = [uc.execute(filename=f"img{i}.png", data=f"data{i}".encode()) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        assert all(r.filename == f"img{i}.png" for i, r in enumerate(results))
        assert upload_count == 10
