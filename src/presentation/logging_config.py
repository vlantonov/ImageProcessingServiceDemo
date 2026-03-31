"""Structured logging configuration with correlation-ID injection.

Provides a :class:`logging.Filter` that attaches the current correlation ID
to every log record and a JSON formatter for machine-readable output.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from src.presentation.api.correlation import get_correlation_id


class CorrelationIdFilter(logging.Filter):
    """Inject ``correlation_id`` into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()  # type: ignore[attr-defined]
        return True


class JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        # Ensure exc_info is resolved to a tuple (LogRecord may store True).
        if record.exc_info and not isinstance(record.exc_info, tuple):
            import sys

            record.exc_info = sys.exc_info()

        log_entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", ""),
        }
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def configure_logging(*, json_output: bool = False, level: int = logging.INFO) -> None:
    """Set up root logger with correlation-ID filter.

    Parameters
    ----------
    json_output:
        When *True*, use :class:`JSONFormatter` for structured JSON lines.
        When *False*, use a human-readable format that still includes the
        correlation ID.
    level:
        Root log level.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Remove any existing handlers to avoid duplicate output.
    root.handlers.clear()

    handler = logging.StreamHandler()
    handler.addFilter(CorrelationIdFilter())

    if json_output:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [cid=%(correlation_id)s]: %(message)s"
            )
        )

    root.addHandler(handler)
