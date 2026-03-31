"""Tests for correlation-ID middleware and structured logging."""

from __future__ import annotations

import json
import logging
import re
from unittest.mock import patch

import pytest

from src.presentation.api.correlation import (
    HEADER_NAME,
    correlation_id_ctx,
    get_correlation_id,
    new_correlation_id,
)
from src.presentation.logging_config import (
    CorrelationIdFilter,
    JSONFormatter,
    configure_logging,
)

# ── correlation module ────────────────────────────────────────────────────


class TestCorrelationId:
    def test_new_correlation_id_is_hex(self):
        cid = new_correlation_id()
        assert re.fullmatch(r"[0-9a-f]{32}", cid)

    def test_new_ids_are_unique(self):
        assert new_correlation_id() != new_correlation_id()

    def test_get_returns_empty_by_default(self):
        assert get_correlation_id() == ""

    def test_context_var_round_trip(self):
        token = correlation_id_ctx.set("test-id-123")
        try:
            assert get_correlation_id() == "test-id-123"
        finally:
            correlation_id_ctx.reset(token)
        assert get_correlation_id() == ""

    def test_header_name(self):
        assert HEADER_NAME == "X-Correlation-ID"


# ── logging filter & formatter ────────────────────────────────────────────


class TestCorrelationIdFilter:
    def test_filter_adds_correlation_id(self):
        filt = CorrelationIdFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        token = correlation_id_ctx.set("abc123")
        try:
            result = filt.filter(record)
        finally:
            correlation_id_ctx.reset(token)
        assert result is True
        assert record.correlation_id == "abc123"  # type: ignore[attr-defined]

    def test_filter_empty_when_no_context(self):
        filt = CorrelationIdFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        filt.filter(record)
        assert record.correlation_id == ""  # type: ignore[attr-defined]


class TestJSONFormatter:
    def test_output_is_valid_json(self):
        fmt = JSONFormatter()
        record = logging.LogRecord("mylogger", logging.WARNING, "", 0, "hello", (), None)
        record.correlation_id = "cid-42"  # type: ignore[attr-defined]
        line = fmt.format(record)
        data = json.loads(line)
        assert data["level"] == "WARNING"
        assert data["logger"] == "mylogger"
        assert data["message"] == "hello"
        assert data["correlation_id"] == "cid-42"
        assert "timestamp" in data

    def test_exception_included(self):
        import sys

        fmt = JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()
            record = logging.LogRecord("x", logging.ERROR, "", 0, "err", (), exc_info=exc_info)
        record.correlation_id = ""  # type: ignore[attr-defined]
        data = json.loads(fmt.format(record))
        assert "exception" in data
        assert "boom" in data["exception"]


class TestConfigureLogging:
    def test_configure_text_format(self):
        configure_logging(json_output=False, level=logging.DEBUG)
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1
        assert any(isinstance(f, CorrelationIdFilter) for f in root.handlers[0].filters)

    def test_configure_json_format(self):
        configure_logging(json_output=True, level=logging.INFO)
        root = logging.getLogger()
        handler = root.handlers[0]
        assert isinstance(handler.formatter, JSONFormatter)


# ── middleware integration via TestClient ──────────────────────────────────


@pytest.fixture
def client(tmp_path):
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock

    from fastapi.testclient import TestClient

    from src.application.dto.image_dto import ImageListResponse
    from src.application.use_cases.list_images import ListImagesUseCase
    from src.config import Settings
    from src.main import app
    from src.presentation.api.dependencies import get_list_use_case, get_settings
    from src.presentation.schemas.image_schemas import ComponentCheck

    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    app.router.lifespan_context = _noop_lifespan

    mock_list = AsyncMock(spec=ListImagesUseCase)
    mock_list.execute = AsyncMock(
        return_value=ImageListResponse(images=[], total=0, offset=0, limit=50)
    )
    app.dependency_overrides[get_list_use_case] = lambda: mock_list

    test_settings = Settings(storage_base_dir=str(tmp_path))
    app.dependency_overrides[get_settings] = lambda: test_settings

    async def _ok_db():
        return ComponentCheck(status="ok")

    with patch("src.presentation.api.routes.health._check_database", side_effect=_ok_db):
        yield TestClient(app)
    app.dependency_overrides.clear()


class TestMiddlewareCorrelation:
    def test_generates_correlation_id_when_missing(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        cid = resp.headers.get(HEADER_NAME)
        assert cid is not None
        assert len(cid) == 32

    def test_echoes_provided_correlation_id(self, client):
        resp = client.get("/health", headers={HEADER_NAME: "my-trace-id-999"})
        assert resp.headers[HEADER_NAME] == "my-trace-id-999"

    def test_correlation_id_in_response_for_api_routes(self, client):
        resp = client.get("/api/v1/images/")
        assert HEADER_NAME in resp.headers
