"""Tests for health check routes — DB failure and storage directory missing."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.config import Settings
from src.main import app
from src.presentation.api.dependencies import get_settings
from src.presentation.api.routes.health import _check_database, _check_storage


class TestCheckDatabase:
    async def test_check_database_returns_error_on_exception(self):
        def mock_factory():
            return AsyncMock(
                __aenter__=AsyncMock(side_effect=RuntimeError("conn refused")),
                __aexit__=AsyncMock(),
            )

        with patch(
            "src.presentation.api.routes.health._session_factory", return_value=mock_factory
        ):
            result = await _check_database()
            assert result.status == "error"
            assert "conn refused" in (result.detail or "")


class TestCheckStorage:
    def test_check_storage_ok_with_existing_dir(self, tmp_path):
        settings = Settings(
            storage_base_dir=str(tmp_path),
            db_user="test",
            db_password="test",
        )
        result = _check_storage(settings)
        assert result.status == "ok"

    def test_check_storage_error_with_missing_dir(self, tmp_path):
        missing = tmp_path / "nonexistent_dir"
        settings = Settings(
            storage_base_dir=str(missing),
            db_user="test",
            db_password="test",
        )
        result = _check_storage(settings)
        assert result.status == "error"
        assert "not found" in (result.detail or "")


class TestHealthEndpointDegraded:
    def test_health_degraded_when_db_fails(self, tmp_path):
        @asynccontextmanager
        async def _noop_lifespan(a):
            yield

        app.router.lifespan_context = _noop_lifespan

        test_settings = Settings(
            storage_base_dir=str(tmp_path),
            db_user="test",
            db_password="test",
        )
        app.dependency_overrides[get_settings] = lambda: test_settings

        from src.presentation.schemas.image_schemas import ComponentCheck

        async def _fail_db_check():
            return ComponentCheck(status="error", detail="conn refused")

        with patch(
            "src.presentation.api.routes.health._check_database", side_effect=_fail_db_check
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "degraded"
            assert data["checks"]["database"]["status"] == "error"

        app.dependency_overrides.clear()

    def test_health_degraded_when_storage_missing(self, tmp_path):
        @asynccontextmanager
        async def _noop_lifespan(a):
            yield

        app.router.lifespan_context = _noop_lifespan

        missing = tmp_path / "nonexistent"
        test_settings = Settings(
            storage_base_dir=str(missing),
            db_user="test",
            db_password="test",
        )
        app.dependency_overrides[get_settings] = lambda: test_settings

        from src.presentation.schemas.image_schemas import ComponentCheck

        async def _ok_db_check():
            return ComponentCheck(status="ok")

        with patch("src.presentation.api.routes.health._check_database", side_effect=_ok_db_check):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "degraded"
            assert data["checks"]["storage"]["status"] == "error"

        app.dependency_overrides.clear()
