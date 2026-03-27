"""Tests for the Image domain entity."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.domain.entities.image import Image, ImageMetadata, ProcessingStatus


class TestImage:
    def test_initial_state(self):
        img = Image(filename="photo.jpg", original_path="/data/photo.jpg")
        assert img.status == ProcessingStatus.PENDING
        assert img.metadata is None
        assert img.thumbnail_path is None
        assert img.tags == []

    def test_mark_processing(self):
        img = Image(filename="photo.jpg", original_path="/data/photo.jpg")
        img.mark_processing()
        assert img.status == ProcessingStatus.PROCESSING

    def test_mark_completed(self):
        img = Image(filename="photo.jpg", original_path="/data/photo.jpg")
        meta = ImageMetadata(width=800, height=600, format="JPEG", size_bytes=50000, channels=3)
        img.mark_completed("/data/thumb_photo.jpg", meta)
        assert img.status == ProcessingStatus.COMPLETED
        assert img.thumbnail_path == "/data/thumb_photo.jpg"
        assert img.metadata is meta

    def test_mark_failed(self):
        img = Image(filename="photo.jpg", original_path="/data/photo.jpg")
        img.mark_failed()
        assert img.status == ProcessingStatus.FAILED

    def test_is_expired_no_expiry(self):
        img = Image(filename="photo.jpg", original_path="/data/photo.jpg")
        assert img.is_expired() is False

    def test_is_expired_future(self):
        future = datetime.now(UTC) + timedelta(hours=24)
        img = Image(filename="photo.jpg", original_path="/data/photo.jpg", expires_at=future)
        assert img.is_expired() is False

    def test_is_expired_past(self):
        past = datetime.now(UTC) - timedelta(hours=1)
        img = Image(filename="photo.jpg", original_path="/data/photo.jpg", expires_at=past)
        assert img.is_expired() is True

    def test_updated_at_changes_on_state_transition(self):
        img = Image(filename="photo.jpg", original_path="/data/photo.jpg")
        original = img.updated_at
        img.mark_processing()
        assert img.updated_at >= original
