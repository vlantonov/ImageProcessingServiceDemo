"""Middleware that records RED metrics for every HTTP request."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.infrastructure.observability.metrics import (
    active_requests,
    request_duration,
    request_errors_total,
    request_total,
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request duration, count, and error rate as OpenTelemetry metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in ("/health", "/metrics"):
            return await call_next(request)

        attrs = {"method": request.method, "path": request.url.path}
        active_requests.add(1, attrs)
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            request_errors_total.add(1, {**attrs, "status_code": "500"})
            active_requests.add(-1, attrs)
            raise

        elapsed = time.perf_counter() - start
        status_code = str(response.status_code)

        request_duration.record(elapsed, {**attrs, "status_code": status_code})
        request_total.add(1, {**attrs, "status_code": status_code})

        if response.status_code >= 400:
            request_errors_total.add(1, {**attrs, "status_code": status_code})

        active_requests.add(-1, attrs)
        return response
