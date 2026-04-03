"""Integration test for the FastAPI application lifespan (startup/shutdown)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.main import lifespan


class TestLifespan:
    async def test_startup_and_shutdown_cleans_up(self):
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
                pass

            # After exiting: shutdown_executor was called
            mock_shutdown.assert_called_once()

        await engine.dispose()

    async def test_shutdown_disposes_engine_and_executor(self):
        """Verify engine.dispose() and shutdown_executor are called during shutdown."""
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        original_dispose = engine.dispose
        mock_dispose = AsyncMock(side_effect=original_dispose)
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

    async def test_lifespan_logs_startup_message(self, caplog: pytest.LogCaptureFixture):
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
            patch("src.infrastructure.processing.pillow_processor.shutdown_executor"),
            caplog.at_level("INFO"),
        ):
            async with lifespan(mock_app):
                pass

        assert any("Application startup complete" in msg for msg in caplog.messages)
        await engine.dispose()
