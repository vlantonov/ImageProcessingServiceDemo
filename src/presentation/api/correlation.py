"""Correlation ID context for distributed tracing.

Stores a per-request correlation ID in a :class:`contextvars.ContextVar` so
that every log record emitted during request processing can include the same
trace identifier — even across ``await`` boundaries and thread pool executors.
"""

from __future__ import annotations

import contextvars
import uuid

correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)

HEADER_NAME = "X-Correlation-ID"


def new_correlation_id() -> str:
    """Generate a new random correlation ID."""
    return uuid.uuid4().hex


def get_correlation_id() -> str:
    """Return the current correlation ID (empty string if unset)."""
    return correlation_id_ctx.get()
