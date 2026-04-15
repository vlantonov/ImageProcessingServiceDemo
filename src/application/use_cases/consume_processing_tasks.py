"""Use case: consume image-processing tasks from a message queue.

In production, this is run as a standalone Kafka consumer worker — fully
decoupled from the HTTP ingestion path.
"""

from __future__ import annotations

import json
import logging
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

        try:
            payload = json.loads(message.value)
            image_id = uuid.UUID(payload["image_id"])
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.error("Malformed processing message, skipping: %s", exc)
            return True  # consumed but discarded

        logger.info("Consumed processing task for image %s", image_id)
        try:
            await self._process_use_case.execute(image_id)
        except Exception:
            logger.exception("Processing failed for image %s", image_id)

        return True
