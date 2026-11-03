"""Kafka-backed message broker adapter.

Uses ``aiokafka`` for async Kafka producer/consumer.  In production,
the HTTP server only needs the *producer*, while a separate worker
process runs the *consumer*.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from aiokafka import (  # type: ignore[import-untyped]
    AIOKafkaConsumer,
    AIOKafkaProducer,
    ConsumerRebalanceListener,
    TopicPartition,
)

from src.domain.interfaces.message_broker import Message, MessageBroker

logger = logging.getLogger(__name__)


class _MetricsRebalanceListener(ConsumerRebalanceListener):
    def __init__(self, group: str) -> None:
        self._group = group

    async def on_partitions_revoked(self, revoked: Iterable[TopicPartition]) -> None:
        revoked_list = list(revoked)
        KafkaMessageBroker._record_consumer_rebalance(
            group=self._group,
            event="revoked",
            partitions_count=len(revoked_list),
        )

    async def on_partitions_assigned(self, assigned: Iterable[TopicPartition]) -> None:
        assigned_list = list(assigned)
        KafkaMessageBroker._record_consumer_rebalance(
            group=self._group,
            event="assigned",
            partitions_count=len(assigned_list),
        )


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
                rebalance_listener=_MetricsRebalanceListener(self._consumer_group),
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

        topic_partition = TopicPartition(record.topic, record.partition)
        highwater = consumer.highwater(topic_partition)
        if highwater is not None:
            lag = max(highwater - record.offset - 1, 0)
            self._record_consumer_lag(
                topic=record.topic,
                partition=record.partition,
                group=self._consumer_group,
                lag=lag,
            )

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

    @staticmethod
    def _record_consumer_lag(
        *,
        topic: str,
        partition: int,
        group: str,
        lag: int,
    ) -> None:
        try:
            from src.infrastructure.observability.metrics import broker_consumer_lag_messages

            broker_consumer_lag_messages.record(
                lag,
                {"topic": topic, "partition": str(partition), "group": group},
            )
        except Exception:
            logger.debug("Failed to record consumer lag metric", exc_info=True)

    @staticmethod
    def _record_consumer_rebalance(
        *,
        group: str,
        event: str,
        partitions_count: int,
    ) -> None:
        try:
            from src.infrastructure.observability.metrics import broker_consumer_rebalances

            broker_consumer_rebalances.add(
                1,
                {
                    "group": group,
                    "event": event,
                    "partitions_count": str(partitions_count),
                },
            )
        except Exception:
            logger.debug("Failed to record consumer rebalance metric", exc_info=True)
