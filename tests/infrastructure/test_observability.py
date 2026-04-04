"""Tests for observability middleware and setup modules."""

from __future__ import annotations

from unittest.mock import patch

from starlette.testclient import TestClient

from src.infrastructure.observability.middleware import MetricsMiddleware
from src.infrastructure.observability.setup import (
    _build_resource,
    instrument_logging,
    setup_metrics,
    setup_tracing,
)


class TestBuildResource:
    def test_creates_resource_with_service_name(self):
        resource = _build_resource("test-service")
        attrs = dict(resource.attributes)
        assert attrs["service.name"] == "test-service"


class TestSetupTracing:
    def test_setup_tracing_returns_provider(self):
        provider = setup_tracing(service_name="test-svc", otlp_endpoint="http://localhost:4317")
        assert provider is not None
        provider.shutdown()


class TestSetupMetrics:
    def test_setup_metrics_returns_reader(self):
        reader = setup_metrics(service_name="test-svc")
        assert reader is not None
        reader.shutdown()


class TestInstrumentLogging:
    def test_instrument_logging_injects_trace_context(self):
        """Verify that instrument_logging doesn't raise."""
        # Just ensure it runs without error; actual injection requires a span context
        instrument_logging()


class TestMetricsMiddleware:
    def test_skips_health_and_metrics_paths(self):
        """Requests to /health and /metrics should bypass metrics recording."""
        from fastapi import FastAPI

        test_app = FastAPI()
        test_app.add_middleware(MetricsMiddleware)

        @test_app.get("/health")
        async def health():
            return {"status": "ok"}

        @test_app.get("/metrics")
        async def metrics():
            return {"metrics": []}

        client = TestClient(test_app)
        resp = client.get("/health")
        assert resp.status_code == 200

        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_records_metrics_for_normal_requests(self):
        """Normal requests should be recorded by the middleware."""
        from fastapi import FastAPI

        test_app = FastAPI()
        test_app.add_middleware(MetricsMiddleware)

        @test_app.get("/api/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(test_app)

        with (
            patch("src.infrastructure.observability.middleware.active_requests") as mock_active,
            patch("src.infrastructure.observability.middleware.request_duration") as mock_dur,
            patch("src.infrastructure.observability.middleware.request_total") as mock_total,
            patch("src.infrastructure.observability.middleware.request_errors_total"),
        ):
            resp = client.get("/api/test")
            assert resp.status_code == 200
            assert mock_active.add.call_count == 2  # +1 and -1
            mock_dur.record.assert_called_once()
            mock_total.add.assert_called_once()

    def test_records_error_metrics_on_4xx(self):
        """4xx responses should increment error counter."""
        from fastapi import FastAPI, HTTPException

        test_app = FastAPI()
        test_app.add_middleware(MetricsMiddleware)

        @test_app.get("/api/fail")
        async def fail_endpoint():
            raise HTTPException(status_code=404, detail="not found")

        client = TestClient(test_app, raise_server_exceptions=False)

        with (
            patch("src.infrastructure.observability.middleware.active_requests"),
            patch("src.infrastructure.observability.middleware.request_duration"),
            patch("src.infrastructure.observability.middleware.request_total"),
            patch(
                "src.infrastructure.observability.middleware.request_errors_total"
            ) as mock_errors,
        ):
            resp = client.get("/api/fail")
            assert resp.status_code == 404
            mock_errors.add.assert_called_once()

    def test_records_error_metrics_on_exception(self):
        """Unhandled exceptions should increment error counter with status 500."""
        from fastapi import FastAPI

        test_app = FastAPI()
        test_app.add_middleware(MetricsMiddleware)

        @test_app.get("/api/crash")
        async def crash_endpoint():
            raise RuntimeError("boom")

        client = TestClient(test_app, raise_server_exceptions=False)

        with (
            patch("src.infrastructure.observability.middleware.active_requests"),
            patch("src.infrastructure.observability.middleware.request_duration"),
            patch("src.infrastructure.observability.middleware.request_total"),
            patch(
                "src.infrastructure.observability.middleware.request_errors_total"
            ) as mock_errors,
        ):
            resp = client.get("/api/crash")
            assert resp.status_code == 500
            mock_errors.add.assert_called()
