"""In-memory sliding-window rate limiter for FastAPI."""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status


class RateLimiter:
    """Sliding-window rate limiter keyed by client IP.

    Parameters
    ----------
    max_requests : int
        Maximum number of requests allowed in the time window.
    window_seconds : int
        Length of the sliding window in seconds.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup(self, key: str, now: float) -> None:
        cutoff = now - self._window_seconds
        timestamps = self._requests[key]
        # Remove expired timestamps
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)
        if not timestamps:
            del self._requests[key]

    async def __call__(self, request: Request) -> None:
        now = time.monotonic()
        key = self._client_ip(request)

        with self._lock:
            self._cleanup(key, now)
            timestamps = self._requests[key]

            if len(timestamps) >= self._max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Try again later.",
                )
            timestamps.append(now)
