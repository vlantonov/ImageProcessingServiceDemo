"""Tests for the rate limiter."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.presentation.api.rate_limit import RateLimiter


@pytest.fixture
def limiter() -> RateLimiter:
    return RateLimiter(max_requests=3, window_seconds=60)


@pytest.fixture
def rate_app(limiter: RateLimiter) -> FastAPI:
    """Minimal FastAPI app with a rate-limited endpoint."""
    app = FastAPI()

    @app.get("/limited")
    async def limited(_: None = Depends(limiter)):
        return {"ok": True}

    return app


@pytest.fixture
def rate_client(rate_app: FastAPI) -> TestClient:
    return TestClient(rate_app)


class TestRateLimiter:
    def test_allows_requests_within_limit(self, rate_client: TestClient) -> None:
        for _ in range(3):
            resp = rate_client.get("/limited")
            assert resp.status_code == 200

    def test_blocks_requests_over_limit(self, rate_client: TestClient) -> None:
        for _ in range(3):
            rate_client.get("/limited")

        resp = rate_client.get("/limited")
        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()["detail"]

    def test_window_expires_allows_new_requests(self) -> None:
        limiter = RateLimiter(max_requests=2, window_seconds=1)
        app = FastAPI()

        @app.get("/limited")
        async def limited(_: None = Depends(limiter)):
            return {"ok": True}

        client = TestClient(app)

        # Use up the quota
        for _ in range(2):
            client.get("/limited")

        assert client.get("/limited").status_code == 429

        # Advance time past the window via monotonic mock
        with patch("src.presentation.api.rate_limit.time") as mock_time:
            mock_time.monotonic.return_value = time.monotonic() + 2
            resp = client.get("/limited")
            assert resp.status_code == 200

    def test_separate_clients_have_separate_limits(self) -> None:
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        app = FastAPI()

        @app.get("/limited")
        async def limited(_: None = Depends(limiter)):
            return {"ok": True}

        client = TestClient(app)

        # First client at 127.0.0.1 (default for TestClient)
        resp = client.get("/limited")
        assert resp.status_code == 200
        assert client.get("/limited").status_code == 429

        # Different client IP via X-Forwarded-For
        resp = client.get("/limited", headers={"X-Forwarded-For": "10.0.0.1"})
        assert resp.status_code == 200

    def test_x_forwarded_for_uses_first_ip(self) -> None:
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        app = FastAPI()

        @app.get("/limited")
        async def limited(_: None = Depends(limiter)):
            return {"ok": True}

        client = TestClient(app)

        resp = client.get("/limited", headers={"X-Forwarded-For": "192.168.1.1, 10.0.0.1"})
        assert resp.status_code == 200

        resp = client.get("/limited", headers={"X-Forwarded-For": "192.168.1.1, 10.0.0.1"})
        assert resp.status_code == 429
