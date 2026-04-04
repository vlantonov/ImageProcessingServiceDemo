"""Tests for application config, session, dependencies, and main module gaps."""

from __future__ import annotations

import os
from unittest.mock import patch

from src.config import Settings


class TestSettingsDatabaseUrl:
    def test_database_url_computed(self):
        s = Settings(
            db_user="admin",
            db_password="secret",
            db_host="db.local",
            db_port=5433,
            db_name="mydb",
        )
        assert s.database_url == "postgresql+asyncpg://admin:secret@db.local:5433/mydb"

    def test_database_url_special_chars_encoded(self):
        s = Settings(db_user="admin", db_password="p@ss:w/rd", db_host="localhost")
        url = s.database_url
        assert "p%40ss%3Aw%2Frd" in url


class TestBuildEngineAndSession:
    def test_build_engine(self):
        from src.infrastructure.database.session import build_engine

        s = Settings(db_user="test", db_password="test")
        engine = build_engine(s)
        assert engine is not None
        # Just verify it's an async engine with the right URL prefix
        assert "asyncpg" in str(engine.url)

    def test_build_session_factory(self):
        from src.infrastructure.database.session import build_engine, build_session_factory

        s = Settings(db_user="test", db_password="test")
        engine = build_engine(s)
        factory = build_session_factory(engine)
        assert factory is not None


class TestCreateApp:
    def test_create_app_basic(self):
        """create_app returns a FastAPI app without OTel."""
        from src.main import create_app

        env = {"IMG_DB_USER": "test", "IMG_DB_PASSWORD": "test"}
        with (
            patch.dict(os.environ, env, clear=False),
            patch("src.main._is_otel_enabled", return_value=False),
            patch("src.main._is_cors_enabled", return_value=False),
        ):
            from src.presentation.api.dependencies import get_settings

            get_settings.cache_clear()
            app = create_app()
            assert app.title == "Image Processing Service"

    def test_create_app_with_cors(self):
        """create_app adds CORS middleware when enabled."""
        from src.main import create_app

        env = {
            "IMG_DB_USER": "test",
            "IMG_DB_PASSWORD": "test",
            "IMG_CORS_ORIGINS": '["http://localhost:3000"]',
        }
        with (
            patch("src.main._is_otel_enabled", return_value=False),
            patch("src.main._is_cors_enabled", return_value=True),
            patch.dict(os.environ, env, clear=False),
        ):
            from src.presentation.api.dependencies import get_settings

            get_settings.cache_clear()
            app = create_app()
            assert app is not None


class TestIsOtelEnabled:
    def test_otel_disabled_by_default(self):
        from src.main import _is_otel_enabled

        with patch.dict(os.environ, {}, clear=True):
            assert _is_otel_enabled() is False

    def test_otel_enabled_with_true(self):
        from src.main import _is_otel_enabled

        with patch.dict(os.environ, {"IMG_OTEL_ENABLED": "true"}, clear=False):
            assert _is_otel_enabled() is True

    def test_otel_enabled_with_1(self):
        from src.main import _is_otel_enabled

        with patch.dict(os.environ, {"IMG_OTEL_ENABLED": "1"}, clear=False):
            assert _is_otel_enabled() is True


class TestIsCorsEnabled:
    def test_cors_disabled_by_default(self):
        from src.main import _is_cors_enabled

        with patch.dict(os.environ, {}, clear=True):
            assert _is_cors_enabled() is False

    def test_cors_enabled_when_origins_set(self):
        from src.main import _is_cors_enabled

        with patch.dict(os.environ, {"IMG_CORS_ORIGINS": "http://localhost"}, clear=False):
            assert _is_cors_enabled() is True


class TestLoggingConfig:
    def test_json_formatter_basic(self):
        import logging

        from src.presentation.logging_config import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "hello world" in output
        assert "timestamp" in output

    def test_json_formatter_with_exc_info_as_true(self):
        """When exc_info is True (not a tuple), the formatter should resolve it."""
        import logging

        from src.presentation.logging_config import JSONFormatter

        formatter = JSONFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="fail",
                args=(),
                exc_info=True,
            )
            output = formatter.format(record)
            assert "fail" in output


class TestInMemoryCacheEvictOldestEmpty:
    def test_evict_oldest_on_empty_store_does_nothing(self):
        from src.infrastructure.cache.in_memory_cache import InMemoryImageCache

        cache = InMemoryImageCache(ttl_seconds=60, max_size=10)
        # Should not raise
        cache._evict_oldest()
