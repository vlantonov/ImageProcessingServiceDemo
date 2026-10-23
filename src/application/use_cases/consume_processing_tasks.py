"""Use case: consume image-processing tasks from a message queue.

In production, this is run as a standalone Kafka consumer worker — fully
decoupled from the HTTP ingestion path.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from src.application.use_cases.process_image import ProcessImageUseCase
from src.domain.interfaces.message_broker import Message, MessageBroker

logger = logging.getLogger(__name__)

IMAGE_PROCESSING_TOPIC = "image.processing"
IMAGE_PROCESSING_DLQ_TOPIC = "image.processing.dlq"
DEFAULT_RETRY_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 1.0


class ConsumeProcessingTasksUseCase:
    """Pull messages from the processing queue and process images."""

    def __init__(
        self,
        broker: MessageBroker,
        process_use_case: ProcessImageUseCase,
        retry_max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS,
        retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
        dlq_topic: str = IMAGE_PROCESSING_DLQ_TOPIC,
    ) -> None:
        self._broker = broker
        self._process_use_case = process_use_case
        self._retry_max_attempts = max(retry_max_attempts, 0)
        self._retry_backoff_seconds = max(retry_backoff_seconds, 0.0)
        self._dlq_topic = dlq_topic

    async def execute_once(self) -> bool:
        """Consume and process a single message.

        Returns ``True`` if a message was processed, ``False`` if the queue
        was empty.
        """
        message = await self._broker.consume(IMAGE_PROCESSING_TOPIC)
        if message is None:
            return False

        self._record_consumed(IMAGE_PROCESSING_TOPIC)
        start = time.perf_counter()

        try:
            image_id, attempt, payload = self._parse_payload(message)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.error("Malformed processing message, moving to DLQ: %s", exc)
            self._record_consume_error(IMAGE_PROCESSING_TOPIC, reason="malformed")
            await self._publish_dead_letter_message(
                message=message,
                reason="malformed",
                error=str(exc),
                payload={},
            )
            elapsed = time.perf_counter() - start
            self._record_processing_duration(elapsed, IMAGE_PROCESSING_TOPIC)
            return True  # consumed but discarded

        logger.info("Consumed processing task for image %s", image_id)
        try:
            await self._process_use_case.execute(image_id)
        except Exception as exc:
            logger.exception("Processing failed for image %s", image_id)
            self._record_consume_error(IMAGE_PROCESSING_TOPIC, reason="processing_failed")
            await self._handle_retry_or_dlq(
                message=message,
                image_id=image_id,
                attempt=attempt,
                payload=payload,
                processing_error=exc,
            )

        elapsed = time.perf_counter() - start
        self._record_processing_duration(elapsed, IMAGE_PROCESSING_TOPIC)

        return True

    @staticmethod
    def _parse_payload(message: Message) -> tuple[uuid.UUID, int, dict[str, Any]]:
        payload = json.loads(message.value)
        if not isinstance(payload, dict):
            raise ValueError("message payload must be a JSON object")

        image_id = uuid.UUID(str(payload["image_id"]))
        attempt = payload.get("attempt", 0)
        if not isinstance(attempt, int) or attempt < 0:
            raise ValueError("attempt must be a non-negative integer")

        return image_id, attempt, payload

    async def _handle_retry_or_dlq(
        self,
        *,
        message: Message,
        image_id: uuid.UUID,
        attempt: int,
        payload: dict[str, Any],
        processing_error: Exception,
    ) -> None:
        if attempt < self._retry_max_attempts:
            await self._publish_retry_message(message, image_id, attempt + 1)
            return

        await self._publish_dead_letter_message(
            message=message,
            reason="retries_exhausted",
            error=str(processing_error),
            payload=payload,
        )

    async def _publish_retry_message(
        self,
        message: Message,
        image_id: uuid.UUID,
        next_attempt: int,
    ) -> None:
        delay_seconds = self._retry_backoff_seconds * (2 ** (next_attempt - 1))
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

        retry_payload = {"image_id": str(image_id), "attempt": next_attempt}
        try:
            await self._broker.publish(
                Message(
                    topic=IMAGE_PROCESSING_TOPIC,
                    key=message.key or str(image_id),
                    value=json.dumps(retry_payload).encode(),
                )
            )
            self._record_retried(IMAGE_PROCESSING_TOPIC)
            logger.warning(
                "Republished processing task for image %s with retry attempt %d/%d",
                image_id,
                next_attempt,
                self._retry_max_attempts,
            )
        except Exception as exc:
            logger.exception("Failed to publish retry message for image %s", image_id)
            self._record_consume_error(IMAGE_PROCESSING_TOPIC, reason="retry_publish_failed")
            await self._publish_dead_letter_message(
                message=message,
                reason="retry_publish_failed",
                error=str(exc),
                payload=retry_payload,
            )

    async def _publish_dead_letter_message(
        self,
        *,
        message: Message,
        reason: str,
        error: str,
        payload: dict[str, Any],
    ) -> None:
        dead_letter_payload = {
            "dead_lettered_at": datetime.now(UTC).isoformat(),
            "reason": reason,
            "error": error,
            "original_topic": IMAGE_PROCESSING_TOPIC,
            "original_key": message.key,
            "original_value": message.value.decode(errors="replace"),
            "payload": payload,
        }
        try:
            await self._broker.publish(
                Message(
                    topic=self._dlq_topic,
                    key=message.key,
                    value=json.dumps(dead_letter_payload).encode(),
                )
            )
            self._record_dead_letter(self._dlq_topic, reason=reason)
            logger.error(
                "Message sent to DLQ topic '%s' (reason=%s key=%s)",
                self._dlq_topic,
                reason,
                message.key,
            )
        except Exception:
            logger.exception(
                "Failed to publish dead-letter message to topic '%s'",
                self._dlq_topic,
            )
            self._record_consume_error(IMAGE_PROCESSING_TOPIC, reason="dlq_publish_failed")

    @staticmethod
    def _record_consumed(topic: str) -> None:
        try:
            from src.infrastructure.observability.metrics import broker_messages_consumed

            broker_messages_consumed.add(1, {"topic": topic})
        except Exception:
            pass

    @staticmethod
    def _record_consume_error(topic: str, *, reason: str) -> None:
        try:
            from src.infrastructure.observability.metrics import broker_consume_errors

            broker_consume_errors.add(1, {"topic": topic, "reason": reason})
        except Exception:
            pass

    @staticmethod
    def _record_processing_duration(elapsed: float, topic: str) -> None:
        try:
            from src.infrastructure.observability.metrics import (
                broker_consumer_processing_duration,
            )

            broker_consumer_processing_duration.record(elapsed, {"topic": topic})
        except Exception:
            pass

    @staticmethod
    def _record_retried(topic: str) -> None:
        try:
            from src.infrastructure.observability.metrics import broker_messages_retried

            broker_messages_retried.add(1, {"topic": topic})
        except Exception:
            pass

    @staticmethod
    def _record_dead_letter(topic: str, *, reason: str) -> None:
        try:
            from src.infrastructure.observability.metrics import broker_messages_dead_lettered

            broker_messages_dead_lettered.add(1, {"topic": topic, "reason": reason})
        except Exception:
            pass
