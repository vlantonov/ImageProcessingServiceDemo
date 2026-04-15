"""In-memory message broker for testing and local development.

Messages are stored in an ``asyncio.Queue`` per topic — no external
services required.
"""

from __future__ import annotations

import asyncio
import logging

from src.domain.interfaces.message_broker import Message, MessageBroker

logger = logging.getLogger(__name__)


class InMemoryMessageBroker(MessageBroker):
    """Queue-backed broker suitable for tests and single-process dev mode."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[Message]] = {}

    def _get_queue(self, topic: str) -> asyncio.Queue[Message]:
        if topic not in self._queues:
            self._queues[topic] = asyncio.Queue()
        return self._queues[topic]

    async def publish(self, message: Message) -> None:
        queue = self._get_queue(message.topic)
        await queue.put(message)
        logger.debug("InMemory publish to %s: key=%s", message.topic, message.key)

    async def consume(self, topic: str) -> Message | None:
        queue = self._get_queue(topic)
        if queue.empty():
            return None
        return queue.get_nowait()

    async def close(self) -> None:
        self._queues.clear()
