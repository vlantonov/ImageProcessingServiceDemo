"""Integration tests for PostgresImageRepository using in-memory SQLite.

Uses aiosqlite to exercise real SQL queries, ORM mapping, and transaction
handling without requiring a running PostgreSQL instance.

Limitations vs real PostgreSQL:
- ARRAY columns are stored as JSON (same list semantics).
- FOR UPDATE SKIP LOCKED is compiled as a no-op (row-locking untested).
- Partial indexes (postgresql_where) are created as regular indexes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import JSON, Uuid
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.sqlite.base import SQLiteCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domain.entities.image import Image, ImageMetadata, ProcessingStatus
from src.infrastructure.database.models import Base, ImageModel
from src.infrastructure.database.postgres_image_repository import PostgresImageRepository

# ---------------------------------------------------------------------------
# SQLite compatibility: make FOR UPDATE a no-op
# ---------------------------------------------------------------------------


def _sqlite_for_update_noop(self, select, **kw):  # type: ignore[no-untyped-def]
    return ""


SQLiteCompiler.for_update_clause = _sqlite_for_update_noop  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _swap_pg_types() -> dict[str, object]:
    """Replace PostgreSQL-specific column types with SQLite equivalents."""
    table = ImageModel.__table__
    originals: dict[str, object] = {}
    for col in table.columns:
        if isinstance(col.type, PG_UUID):
            originals[col.name] = col.type
            col.type = Uuid()
        elif isinstance(col.type, PG_ARRAY):
            originals[col.name] = col.type
            col.type = JSON()
    return originals


def _restore_pg_types(originals: dict[str, object]) -> None:
    table = ImageModel.__table__
    for name, orig_type in originals.items():
        table.columns[name].type = orig_type  # type: ignore[assignment]


@pytest.fixture
async def session_factory():
    originals = _swap_pg_types()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory

    _restore_pg_types(originals)
    await engine.dispose()


@pytest.fixture
def repo(session_factory) -> PostgresImageRepository:
    return PostgresImageRepository(session_factory)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_image(**overrides: object) -> Image:
    return Image(
        id=overrides.get("id", uuid.uuid4()),  # type: ignore[arg-type]
        filename=overrides.get("filename", "test.png"),  # type: ignore[arg-type]
        original_path=overrides.get("original_path", "/data/images/abc_test.png"),  # type: ignore[arg-type]
        status=overrides.get("status", ProcessingStatus.PENDING),  # type: ignore[arg-type]
        tags=overrides.get("tags", ["test"]),  # type: ignore[arg-type]
        created_at=overrides.get("created_at", datetime.now(UTC)),  # type: ignore[arg-type]
        updated_at=overrides.get("updated_at", datetime.now(UTC)),  # type: ignore[arg-type]
        thumbnail_path=overrides.get("thumbnail_path"),  # type: ignore[arg-type]
        metadata=overrides.get("metadata"),  # type: ignore[arg-type]
        expires_at=overrides.get("expires_at"),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Tests: save
# ---------------------------------------------------------------------------


class TestSave:
    async def test_save_new_image(self, repo):
        image = _make_image()
        result = await repo.save(image)
        assert result is image

        fetched = await repo.get_by_id(image.id)
        assert fetched is not None
        assert fetched.id == image.id
        assert fetched.filename == "test.png"

    async def test_save_update_existing(self, repo):
        image = _make_image()
        await repo.save(image)

        image.filename = "updated.png"
        image.status = ProcessingStatus.COMPLETED
        await repo.save(image)

        fetched = await repo.get_by_id(image.id)
        assert fetched.filename == "updated.png"
        assert fetched.status == ProcessingStatus.COMPLETED

    async def test_save_with_metadata(self, repo):
        image = _make_image(
            metadata=ImageMetadata(
                width=1920, height=1080, format="PNG", size_bytes=1234567, channels=3
            )
        )
        await repo.save(image)

        fetched = await repo.get_by_id(image.id)
        assert fetched.metadata is not None
        assert fetched.metadata.width == 1920
        assert fetched.metadata.height == 1080
        assert fetched.metadata.format == "PNG"
        assert fetched.metadata.size_bytes == 1234567
        assert fetched.metadata.channels == 3

    async def test_save_with_thumbnail_and_expires(self, repo):
        expires = datetime.now(UTC) + timedelta(hours=1)
        image = _make_image(
            thumbnail_path="/data/images/thumb_test.png",
            expires_at=expires,
        )
        await repo.save(image)

        fetched = await repo.get_by_id(image.id)
        assert fetched.thumbnail_path == "/data/images/thumb_test.png"
        assert fetched.expires_at is not None


# ---------------------------------------------------------------------------
# Tests: get_by_id
# ---------------------------------------------------------------------------


class TestGetById:
    async def test_get_existing(self, repo):
        image = _make_image()
        await repo.save(image)

        fetched = await repo.get_by_id(image.id)
        assert fetched is not None
        assert fetched.id == image.id

    async def test_get_nonexistent_returns_none(self, repo):
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    async def test_get_preserves_tags(self, repo):
        image = _make_image(tags=["photo", "landscape"])
        await repo.save(image)

        fetched = await repo.get_by_id(image.id)
        assert fetched.tags == ["photo", "landscape"]

    async def test_get_preserves_all_statuses(self, repo):
        for status in ProcessingStatus:
            image = _make_image(status=status)
            await repo.save(image)
            fetched = await repo.get_by_id(image.id)
            assert fetched.status == status


# ---------------------------------------------------------------------------
# Tests: list_images
# ---------------------------------------------------------------------------


class TestListImages:
    async def test_list_empty(self, repo):
        result = await repo.list_images()
        assert result == []

    async def test_list_returns_all(self, repo):
        for i in range(3):
            await repo.save(_make_image(filename=f"img_{i}.png"))

        result = await repo.list_images()
        assert len(result) == 3

    async def test_list_with_offset_and_limit(self, repo):
        for i in range(5):
            await repo.save(_make_image(filename=f"img_{i}.png"))

        result = await repo.list_images(offset=2, limit=2)
        assert len(result) == 2

    async def test_list_filter_by_status(self, repo):
        await repo.save(_make_image(status=ProcessingStatus.PENDING))
        await repo.save(_make_image(status=ProcessingStatus.COMPLETED))
        await repo.save(_make_image(status=ProcessingStatus.PENDING))

        pending = await repo.list_images(status="pending")
        assert len(pending) == 2

        completed = await repo.list_images(status="completed")
        assert len(completed) == 1

    async def test_list_ordered_by_created_at_desc(self, repo):
        now = datetime.now(UTC)
        for i in range(3):
            await repo.save(
                _make_image(
                    filename=f"img_{i}.png",
                    created_at=now - timedelta(hours=2 - i),
                )
            )

        result = await repo.list_images()
        assert result[0].filename == "img_2.png"  # newest first
        assert result[2].filename == "img_0.png"  # oldest last


# ---------------------------------------------------------------------------
# Tests: delete
# ---------------------------------------------------------------------------


class TestDelete:
    async def test_delete_existing(self, repo):
        image = _make_image()
        await repo.save(image)

        result = await repo.delete(image.id)
        assert result is True

        fetched = await repo.get_by_id(image.id)
        assert fetched is None

    async def test_delete_nonexistent_returns_false(self, repo):
        result = await repo.delete(uuid.uuid4())
        assert result is False


# ---------------------------------------------------------------------------
# Tests: get_expired
# ---------------------------------------------------------------------------


class TestGetExpired:
    async def test_returns_expired_images(self, repo):
        past = datetime.now(UTC) - timedelta(hours=1)
        future = datetime.now(UTC) + timedelta(hours=1)

        await repo.save(_make_image(expires_at=past, filename="expired.png"))
        await repo.save(_make_image(expires_at=future, filename="not_expired.png"))
        await repo.save(_make_image(filename="no_expiry.png"))

        expired = await repo.get_expired()
        assert len(expired) == 1
        assert expired[0].filename == "expired.png"

    async def test_respects_batch_size(self, repo):
        past = datetime.now(UTC) - timedelta(hours=1)
        for i in range(5):
            await repo.save(_make_image(expires_at=past, filename=f"exp_{i}.png"))

        expired = await repo.get_expired(batch_size=3)
        assert len(expired) == 3

    async def test_empty_when_none_expired(self, repo):
        future = datetime.now(UTC) + timedelta(hours=1)
        await repo.save(_make_image(expires_at=future))

        expired = await repo.get_expired()
        assert len(expired) == 0


# ---------------------------------------------------------------------------
# Tests: delete_expired_batch (FOR UPDATE SKIP LOCKED is no-op on SQLite)
# ---------------------------------------------------------------------------


class TestDeleteExpiredBatch:
    async def test_deletes_expired_and_returns_entities(self, repo):
        past = datetime.now(UTC) - timedelta(hours=1)
        future = datetime.now(UTC) + timedelta(hours=1)

        await repo.save(_make_image(expires_at=past, filename="expired.png"))
        await repo.save(_make_image(expires_at=future, filename="not_expired.png"))

        deleted = await repo.delete_expired_batch(batch_size=100)
        assert len(deleted) == 1
        assert deleted[0].filename == "expired.png"

        # Verify actually removed from DB
        assert await repo.count() == 1

    async def test_respects_batch_size(self, repo):
        past = datetime.now(UTC) - timedelta(hours=1)
        for _ in range(5):
            await repo.save(_make_image(expires_at=past))

        deleted = await repo.delete_expired_batch(batch_size=2)
        assert len(deleted) == 2
        assert await repo.count() == 3

    async def test_no_expired_returns_empty(self, repo):
        await repo.save(_make_image())

        deleted = await repo.delete_expired_batch()
        assert deleted == []
        assert await repo.count() == 1


# ---------------------------------------------------------------------------
# Tests: count
# ---------------------------------------------------------------------------


class TestCount:
    async def test_count_empty(self, repo):
        assert await repo.count() == 0

    async def test_count_all(self, repo):
        for _ in range(3):
            await repo.save(_make_image())
        assert await repo.count() == 3

    async def test_count_by_status(self, repo):
        await repo.save(_make_image(status=ProcessingStatus.PENDING))
        await repo.save(_make_image(status=ProcessingStatus.COMPLETED))
        await repo.save(_make_image(status=ProcessingStatus.PENDING))

        assert await repo.count(status="pending") == 2
        assert await repo.count(status="completed") == 1
        assert await repo.count(status="failed") == 0


# ---------------------------------------------------------------------------
# Tests: entity-model mapping round-trip
# ---------------------------------------------------------------------------


class TestEntityModelMapping:
    async def test_roundtrip_minimal_entity(self, repo):
        image = _make_image(metadata=None, thumbnail_path=None, tags=[])
        await repo.save(image)

        fetched = await repo.get_by_id(image.id)
        assert fetched.metadata is None
        assert fetched.thumbnail_path is None
        assert fetched.tags == []

    async def test_roundtrip_full_entity(self, repo):
        image = _make_image(
            filename="full.png",
            original_path="/data/full.png",
            thumbnail_path="/data/thumb_full.png",
            metadata=ImageMetadata(
                width=800, height=600, format="JPEG", size_bytes=54321, channels=3
            ),
            status=ProcessingStatus.COMPLETED,
            tags=["portrait", "hdr"],
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        await repo.save(image)

        fetched = await repo.get_by_id(image.id)
        assert fetched.filename == "full.png"
        assert fetched.original_path == "/data/full.png"
        assert fetched.thumbnail_path == "/data/thumb_full.png"
        assert fetched.metadata.width == 800
        assert fetched.metadata.height == 600
        assert fetched.metadata.format == "JPEG"
        assert fetched.metadata.size_bytes == 54321
        assert fetched.metadata.channels == 3
        assert fetched.status == ProcessingStatus.COMPLETED
        assert fetched.tags == ["portrait", "hdr"]
        assert fetched.expires_at is not None

    async def test_empty_tags_stored_as_empty_list(self, repo):
        image = _make_image(tags=[])
        await repo.save(image)

        fetched = await repo.get_by_id(image.id)
        assert fetched.tags == []

    async def test_metadata_with_4_channels(self, repo):
        image = _make_image(
            metadata=ImageMetadata(width=100, height=100, format="PNG", size_bytes=500, channels=4)
        )
        await repo.save(image)

        fetched = await repo.get_by_id(image.id)
        assert fetched.metadata.channels == 4
