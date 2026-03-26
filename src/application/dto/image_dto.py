"""Data Transfer Objects for the application layer."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ImageUploadRequest:
    filename: str
    data: bytes
    tags: list[str]
    ttl_hours: int | None = None


@dataclass(frozen=True)
class ImageResponse:
    id: uuid.UUID
    filename: str
    status: str
    width: int | None
    height: int | None
    format: str | None
    size_bytes: int | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    thumbnail_available: bool


@dataclass(frozen=True)
class ImageListResponse:
    images: list[ImageResponse]
    total: int
    offset: int
    limit: int
