"""Integration test for the FastAPI application lifespan (startup/shutdown)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import JSON, Uuid
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.infrastructure.database.models import Base, ImageModel
from src.main import lifespan


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


class TestLifespan:
    async def test_startup_creates_tables_and_shutdown_cleans_up(self):
        originals = _swap_pg_types()
        try:
            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            mock_app = MagicMock()

            with (
                patch(
                    "src.main.get_settings",
                    return_value=MagicMock(database_url="sqlite+aiosqlite:///:memory:"),
                ),
                patch(
                    "src.infrastructure.database.session.build_engine",
                    return_value=engine,
                ),
                patch(
                    "src.infrastructure.processing.pillow_processor.shutdown_executor",
                ) as mock_shutdown,
            ):
                async with lifespan(mock_app):
                    # Verify tables were created during startup
                    async with engine.begin() as conn:
                        table_names = await conn.run_sync(
                            lambda sync_conn: Base.metadata.tables.keys()
                        )
                    assert "images" in table_names

                # After exiting: shutdown_executor and engine.dispose were called
                mock_shutdown.assert_called_once()
        finally:
            _restore_pg_types(originals)
            await engine.dispose()

    async def test_shutdown_disposes_engine_and_executor(self):
        """Verify engine.dispose() and shutdown_executor are called during shutdown."""
        originals = _swap_pg_types()
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        original_dispose = engine.dispose
        mock_dispose = AsyncMock(side_effect=original_dispose)
        try:
            mock_app = MagicMock()

            with (
                patch(
                    "src.main.get_settings",
                    return_value=MagicMock(database_url="sqlite+aiosqlite:///:memory:"),
                ),
                patch(
                    "src.infrastructure.database.session.build_engine",
                    return_value=engine,
                ),
                patch(
                    "src.infrastructure.processing.pillow_processor.shutdown_executor",
                ) as mock_shutdown,
                patch.object(AsyncEngine, "dispose", mock_dispose),
            ):
                async with lifespan(mock_app):
                    pass

                mock_dispose.assert_awaited_once()
                mock_shutdown.assert_called_once()
        finally:
            _restore_pg_types(originals)

    async def test_lifespan_logs_startup_message(self, caplog: pytest.LogCaptureFixture):
        originals = _swap_pg_types()
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            mock_app = MagicMock()

            with (
                patch(
                    "src.main.get_settings",
                    return_value=MagicMock(database_url="sqlite+aiosqlite:///:memory:"),
                ),
                patch(
                    "src.infrastructure.database.session.build_engine",
                    return_value=engine,
                ),
                patch("src.infrastructure.processing.pillow_processor.shutdown_executor"),
                caplog.at_level("INFO"),
            ):
                async with lifespan(mock_app):
                    pass

            assert any("Database tables ready" in msg for msg in caplog.messages)
        finally:
            _restore_pg_types(originals)
            await engine.dispose()
