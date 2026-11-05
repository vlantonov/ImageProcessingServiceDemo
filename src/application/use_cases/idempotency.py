"""Shared idempotency helpers for application use cases."""

from __future__ import annotations


class IdempotencyConflictError(ValueError):
    """Raised when a key is reused for a different request payload."""


class IdempotencyInProgressError(RuntimeError):
    """Raised when a request with the same key is already in progress."""
