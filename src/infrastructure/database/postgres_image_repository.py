"""Concrete ImageRepository backed by PostgreSQL via SQLAlchemy async."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.entities.image import Image, ImageMetadata, ProcessingStatus
from src.domain.interfaces.image_repository import ImageRepository
from src.infrastructure.database.models import ImageModel


class PostgresImageRepository(ImageRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, image: Image) -> Image:
        async with self._session_factory() as session:
            async with session.begin():
                model = await session.get(ImageModel, image.id)
                if model is None:
                    model = ImageModel(id=image.id)
                    session.add(model)
                _entity_to_model(image, model)
            return image

    async def get_by_id(self, image_id: uuid.UUID) -> Image | None:
        async with self._session_factory() as session:
            model = await session.get(ImageModel, image_id)
            return _model_to_entity(model) if model else None

    async def list_images(
        self, *, offset: int = 0, limit: int = 50, status: str | None = None
    ) -> list[Image]:
        async with self._session_factory() as session:
            stmt = select(ImageModel).order_by(ImageModel.created_at.desc())
            if status:
                stmt = stmt.where(ImageModel.status == status)
            stmt = stmt.offset(offset).limit(limit)
            result = await session.execute(stmt)
            return [_model_to_entity(row) for row in result.scalars().all()]

    async def delete(self, image_id: uuid.UUID) -> bool:
        async with self._session_factory() as session, session.begin():
            stmt = delete(ImageModel).where(ImageModel.id == image_id)
            result = await session.execute(stmt)
            return result.rowcount > 0  # type: ignore[attr-defined]

    async def get_expired(self, batch_size: int = 100) -> list[Image]:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            stmt = (
                select(ImageModel)
                .where(ImageModel.expires_at.isnot(None))
                .where(ImageModel.expires_at <= now)
                .limit(batch_size)
            )
            result = await session.execute(stmt)
            return [_model_to_entity(row) for row in result.scalars().all()]

    async def count(self, *, status: str | None = None) -> int:
        async with self._session_factory() as session:
            stmt = select(func.count()).select_from(ImageModel)
            if status:
                stmt = stmt.where(ImageModel.status == status)
            result = await session.execute(stmt)
            return result.scalar_one()


# ── Mapping helpers ──────────────────────────────────────────────────────────


def _entity_to_model(entity: Image, model: ImageModel) -> None:
    model.filename = entity.filename
    model.original_path = entity.original_path
    model.thumbnail_path = entity.thumbnail_path
    model.status = entity.status.value
    model.tags = entity.tags
    model.created_at = entity.created_at
    model.updated_at = entity.updated_at
    model.expires_at = entity.expires_at
    if entity.metadata:
        model.width = entity.metadata.width
        model.height = entity.metadata.height
        model.format = entity.metadata.format
        model.size_bytes = entity.metadata.size_bytes
        model.channels = entity.metadata.channels


def _model_to_entity(model: ImageModel) -> Image:
    metadata = None
    if model.width is not None:
        metadata = ImageMetadata(
            width=model.width,
            height=model.height or 0,
            format=model.format or "",
            size_bytes=model.size_bytes or 0,
            channels=model.channels or 3,
        )
    return Image(
        id=model.id,
        filename=model.filename,
        original_path=model.original_path,
        thumbnail_path=model.thumbnail_path,
        metadata=metadata,
        status=ProcessingStatus(model.status),
        tags=model.tags or [],
        created_at=model.created_at,
        updated_at=model.updated_at,
        expires_at=model.expires_at,
    )
