"""Kafka-backed message broker adapter.

Uses ``aiokafka`` for async Kafka producer/consumer.  In production,
the HTTP server only needs the *producer*, while a separate worker
process runs the *consumer*.
"""

from __future__ import annotations

import logging

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer  # type: ignore[import-untyped]

from src.domain.interfaces.message_broker import Message, MessageBroker

logger = logging.getLogger(__name__)


class KafkaMessageBroker(MessageBroker):
    """Concrete ``MessageBroker`` backed by Apache Kafka."""

    def __init__(
        self,
        bootstrap_servers: str,
        consumer_group: str = "image-processing",
        consumer_topics: list[str] | None = None,
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._consumer_group = consumer_group
        self._consumer_topics = consumer_topics or []
        self._producer: AIOKafkaProducer | None = None
        self._consumer: AIOKafkaConsumer | None = None

    async def _ensure_producer(self) -> AIOKafkaProducer:
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
            )
            await self._producer.start()
            logger.info("Kafka producer started: %s", self._bootstrap_servers)
        return self._producer

    async def _ensure_consumer(self) -> AIOKafkaConsumer:
        if self._consumer is None:
            self._consumer = AIOKafkaConsumer(
                *self._consumer_topics,
                bootstrap_servers=self._bootstrap_servers,
                group_id=self._consumer_group,
                auto_offset_reset="earliest",
                enable_auto_commit=True,
            )
            await self._consumer.start()
            logger.info(
                "Kafka consumer started: topics=%s group=%s",
                self._consumer_topics,
                self._consumer_group,
            )
        return self._consumer

    async def publish(self, message: Message) -> None:
        producer = await self._ensure_producer()
        await producer.send_and_wait(
            message.topic,
            value=message.value,
            key=message.key.encode() if message.key else None,
        )
        logger.debug("Published to %s: key=%s", message.topic, message.key)

    async def consume(self, topic: str) -> Message | None:
        consumer = await self._ensure_consumer()
        try:
            record = await consumer.getone()
        except Exception:
            logger.exception("Error consuming from Kafka")
            return None

        return Message(
            topic=record.topic,
            key=record.key.decode() if record.key else "",
            value=record.value,
        )

    async def close(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
            logger.info("Kafka producer stopped")
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
            logger.info("Kafka consumer stopped")
