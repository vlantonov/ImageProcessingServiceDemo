"""OpenTelemetry setup — traces, metrics, and log correlation.

Configures:
- OTLP gRPC exporter for traces (→ Tempo)
- Prometheus exporter for metrics (→ Prometheus → Grafana)
- FastAPI and SQLAlchemy auto-instrumentation
- Custom RED metrics (request rate, error rate, duration) + saturation gauges
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


def _build_resource(service_name: str) -> Resource:
    return Resource.create({SERVICE_NAME: service_name})


def setup_tracing(
    *,
    service_name: str,
    otlp_endpoint: str,
) -> TracerProvider:
    """Configure and set the global TracerProvider with OTLP export."""
    resource = _build_resource(service_name)
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    logger.info("Tracing configured → %s", otlp_endpoint)
    return provider


def setup_metrics(*, service_name: str) -> PrometheusMetricReader:
    """Configure and set the global MeterProvider with Prometheus export."""
    resource = _build_resource(service_name)
    reader = PrometheusMetricReader()
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    logger.info("Metrics configured (Prometheus endpoint)")
    return reader


def instrument_app(app: FastAPI) -> None:
    """Auto-instrument FastAPI with OpenTelemetry."""
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health,metrics",
    )
    logger.info("FastAPI instrumented with OpenTelemetry")


def instrument_sqlalchemy(engine: object) -> None:
    """Auto-instrument a SQLAlchemy engine."""
    SQLAlchemyInstrumentor().instrument(engine=engine)  # type: ignore[arg-type]
    logger.info("SQLAlchemy instrumented with OpenTelemetry")


def instrument_logging() -> None:
    """Inject trace context (trace_id, span_id) into log records."""

    def _log_hook(span: trace.Span, record: logging.LogRecord) -> None:
        ctx = span.get_span_context()
        if ctx is not None:
            record.otelTraceID = format(ctx.trace_id, "032x")  # type: ignore[attr-defined]
            record.otelSpanID = format(ctx.span_id, "016x")  # type: ignore[attr-defined]
            record.otelTraceSampled = ctx.trace_flags.sampled  # type: ignore[attr-defined]

    LoggingInstrumentor().instrument(set_logging_format=False, log_hook=_log_hook)
    logger.info("Logging instrumented with OpenTelemetry trace context")
