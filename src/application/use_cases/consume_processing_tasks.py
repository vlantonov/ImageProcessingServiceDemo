"""Use case: consume image-processing tasks from a message queue.

In production, this is run as a standalone Kafka consumer worker — fully
decoupled from the HTTP ingestion path.
"""

from __future__ import annotations

import json
import logging
import time
import uuid

from src.application.use_cases.process_image import ProcessImageUseCase
from src.domain.interfaces.message_broker import MessageBroker

logger = logging.getLogger(__name__)

IMAGE_PROCESSING_TOPIC = "image.processing"


class ConsumeProcessingTasksUseCase:
    """Pull messages from the processing queue and process images."""

    def __init__(
        self,
        broker: MessageBroker,
        process_use_case: ProcessImageUseCase,
    ) -> None:
        self._broker = broker
        self._process_use_case = process_use_case

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
            payload = json.loads(message.value)
            image_id = uuid.UUID(payload["image_id"])
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.error("Malformed processing message, skipping: %s", exc)
            self._record_consume_error(IMAGE_PROCESSING_TOPIC, reason="malformed")
            return True  # consumed but discarded

        logger.info("Consumed processing task for image %s", image_id)
        try:
            await self._process_use_case.execute(image_id)
        except Exception:
            logger.exception("Processing failed for image %s", image_id)
            self._record_consume_error(IMAGE_PROCESSING_TOPIC, reason="processing_failed")
        finally:
            elapsed = time.perf_counter() - start
            self._record_processing_duration(elapsed, IMAGE_PROCESSING_TOPIC)

        return True

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
