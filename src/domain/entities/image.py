"""Image entity — core domain object with no framework dependencies."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ImageMetadata:
    width: int
    height: int
    format: str
    size_bytes: int
    channels: int = 3


@dataclass
class Image:
    """Domain entity representing an uploaded image and its lifecycle."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    filename: str = ""
    original_path: str = ""
    thumbnail_path: str | None = None
    metadata: ImageMetadata | None = None
    status: ProcessingStatus = ProcessingStatus.PENDING
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None

    def mark_processing(self) -> None:
        self.status = ProcessingStatus.PROCESSING
        self._touch()

    def mark_completed(self, thumbnail_path: str, metadata: ImageMetadata) -> None:
        self.status = ProcessingStatus.COMPLETED
        self.thumbnail_path = thumbnail_path
        self.metadata = metadata
        self._touch()

    def mark_failed(self) -> None:
        self.status = ProcessingStatus.FAILED
        self._touch()

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        now = now or datetime.now(timezone.utc)
        return now >= self.expires_at

    def _touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)
