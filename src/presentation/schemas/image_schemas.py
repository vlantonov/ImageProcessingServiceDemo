"""Pydantic schemas for request/response validation at the API boundary."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ImageUploadParams(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=20)
    ttl_hours: int | None = Field(default=None, ge=1, le=8760)


class ImageOut(BaseModel):
    id: uuid.UUID
    filename: str
    status: str
    width: int | None = None
    height: int | None = None
    format: str | None = None
    size_bytes: int | None = None
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    thumbnail_available: bool

    model_config = {"from_attributes": True}


class ImageListOut(BaseModel):
    images: list[ImageOut]
    total: int
    offset: int
    limit: int


class BatchProcessRequest(BaseModel):
    image_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=100)
    concurrency: int = Field(default=8, ge=1, le=32)


class BatchProcessResponse(BaseModel):
    success: int
    failed: int


class RetentionResponse(BaseModel):
    deleted_count: int
    errors: int


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
