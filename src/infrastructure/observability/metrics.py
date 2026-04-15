"""Application-level RED + saturation metrics using OpenTelemetry.

Exposes:
- request_duration_seconds  (histogram)  — latency
- request_total             (counter)    — traffic
- request_errors_total      (counter)    — errors
- active_requests           (up-down counter) — saturation
- image_processing_duration (histogram)  — processing latency
- image_uploads_total       (counter)    — upload traffic
- db_pool_active            (gauge via callback) — DB pool saturation
"""

from __future__ import annotations

from opentelemetry import metrics

_meter = metrics.get_meter("image-processing-service")

# ── Latency ──────────────────────────────────────────────────────────────────
request_duration = _meter.create_histogram(
    name="http_request_duration_seconds",
    description="HTTP request latency in seconds",
    unit="s",
)

image_processing_duration = _meter.create_histogram(
    name="image_processing_duration_seconds",
    description="Image processing latency in seconds",
    unit="s",
)

# ── Traffic ──────────────────────────────────────────────────────────────────
request_total = _meter.create_counter(
    name="http_requests_total",
    description="Total HTTP requests",
)

image_uploads_total = _meter.create_counter(
    name="image_uploads_total",
    description="Total image uploads",
)

# ── Errors ───────────────────────────────────────────────────────────────────
request_errors_total = _meter.create_counter(
    name="http_request_errors_total",
    description="Total HTTP request errors (4xx, 5xx)",
)

# ── Saturation ───────────────────────────────────────────────────────────────
active_requests = _meter.create_up_down_counter(
    name="http_active_requests",
    description="Number of in-flight HTTP requests",
)

images_processing = _meter.create_up_down_counter(
    name="images_currently_processing",
    description="Number of images currently being processed",
)

# ── Message Broker ───────────────────────────────────────────────────────────
broker_messages_published = _meter.create_counter(
    name="broker_messages_published_total",
    description="Total messages published to the message broker",
)

broker_messages_consumed = _meter.create_counter(
    name="broker_messages_consumed_total",
    description="Total messages consumed from the message broker",
)

broker_publish_errors = _meter.create_counter(
    name="broker_publish_errors_total",
    description="Total message publish failures",
)

broker_consume_errors = _meter.create_counter(
    name="broker_consume_errors_total",
    description="Total message consume/processing failures",
)

broker_consumer_processing_duration = _meter.create_histogram(
    name="broker_consumer_processing_duration_seconds",
    description="Time to process a single consumed message end-to-end",
    unit="s",
)
