"""Request logging middleware with correlation-ID propagation."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.presentation.api.correlation import (
    HEADER_NAME,
    correlation_id_ctx,
    new_correlation_id,
)

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cid = request.headers.get(HEADER_NAME) or new_correlation_id()
        token = correlation_id_ctx.set(cid)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            correlation_id_ctx.reset(token)
        elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers[HEADER_NAME] = cid

        logger.info(
            "%s %s → %d (%.1fms) [cid=%s]",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            cid,
        )
        return response
