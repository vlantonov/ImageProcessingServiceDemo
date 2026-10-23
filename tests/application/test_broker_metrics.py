"""Tests for broker metrics recording paths (publish & consume)."""

from __future__ import annotations

from unittest.mock import patch

from src.application.use_cases.consume_processing_tasks import ConsumeProcessingTasksUseCase
from src.application.use_cases.upload_image import UploadImageUseCase


class TestPublishMetrics:
    async def test_record_publish_calls_counter(self):
        with patch("src.infrastructure.observability.metrics.broker_messages_published") as m:
            UploadImageUseCase._record_publish("image.processing")
            m.add.assert_called_once_with(1, {"topic": "image.processing"})

    async def test_record_publish_swallows_error(self):
        with patch(
            "src.infrastructure.observability.metrics.broker_messages_published",
            side_effect=RuntimeError("no OTel"),
        ):
            UploadImageUseCase._record_publish("image.processing")

    async def test_record_publish_error_calls_counter(self):
        with patch("src.infrastructure.observability.metrics.broker_publish_errors") as m:
            UploadImageUseCase._record_publish_error("image.processing")
            m.add.assert_called_once_with(1, {"topic": "image.processing"})

    async def test_record_publish_error_swallows_error(self):
        with patch(
            "src.infrastructure.observability.metrics.broker_publish_errors",
            side_effect=RuntimeError("no OTel"),
        ):
            UploadImageUseCase._record_publish_error("image.processing")


class TestConsumeMetrics:
    async def test_record_consumed_calls_counter(self):
        with patch("src.infrastructure.observability.metrics.broker_messages_consumed") as m:
            ConsumeProcessingTasksUseCase._record_consumed("image.processing")
            m.add.assert_called_once_with(1, {"topic": "image.processing"})

    async def test_record_consumed_swallows_error(self):
        with patch(
            "src.infrastructure.observability.metrics.broker_messages_consumed",
            side_effect=RuntimeError("no OTel"),
        ):
            ConsumeProcessingTasksUseCase._record_consumed("image.processing")

    async def test_record_consume_error_calls_counter(self):
        with patch("src.infrastructure.observability.metrics.broker_consume_errors") as m:
            ConsumeProcessingTasksUseCase._record_consume_error(
                "image.processing", reason="malformed"
            )
            m.add.assert_called_once_with(1, {"topic": "image.processing", "reason": "malformed"})

    async def test_record_consume_error_swallows_error(self):
        with patch(
            "src.infrastructure.observability.metrics.broker_consume_errors",
            side_effect=RuntimeError("no OTel"),
        ):
            ConsumeProcessingTasksUseCase._record_consume_error(
                "image.processing", reason="processing_failed"
            )

    async def test_record_processing_duration_calls_histogram(self):
        with patch(
            "src.infrastructure.observability.metrics.broker_consumer_processing_duration"
        ) as m:
            ConsumeProcessingTasksUseCase._record_processing_duration(0.42, "image.processing")
            m.record.assert_called_once_with(0.42, {"topic": "image.processing"})

    async def test_record_processing_duration_swallows_error(self):
        with patch(
            "src.infrastructure.observability.metrics.broker_consumer_processing_duration",
            side_effect=RuntimeError("no OTel"),
        ):
            ConsumeProcessingTasksUseCase._record_processing_duration(0.42, "image.processing")

    async def test_record_retried_calls_counter(self):
        with patch("src.infrastructure.observability.metrics.broker_messages_retried") as m:
            ConsumeProcessingTasksUseCase._record_retried("image.processing")
            m.add.assert_called_once_with(1, {"topic": "image.processing"})

    async def test_record_retried_swallows_error(self):
        with patch(
            "src.infrastructure.observability.metrics.broker_messages_retried",
            side_effect=RuntimeError("no OTel"),
        ):
            ConsumeProcessingTasksUseCase._record_retried("image.processing")

    async def test_record_dead_letter_calls_counter(self):
        with patch("src.infrastructure.observability.metrics.broker_messages_dead_lettered") as m:
            ConsumeProcessingTasksUseCase._record_dead_letter(
                "image.processing.dlq", reason="retries_exhausted"
            )
            m.add.assert_called_once_with(
                1, {"topic": "image.processing.dlq", "reason": "retries_exhausted"}
            )

    async def test_record_dead_letter_swallows_error(self):
        with patch(
            "src.infrastructure.observability.metrics.broker_messages_dead_lettered",
            side_effect=RuntimeError("no OTel"),
        ):
            ConsumeProcessingTasksUseCase._record_dead_letter(
                "image.processing.dlq", reason="malformed"
            )
