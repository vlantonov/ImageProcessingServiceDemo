"""Tests for Kafka broker metric helper hooks."""

from __future__ import annotations

from unittest.mock import patch

from src.infrastructure.messaging.kafka_message_broker import KafkaMessageBroker


class TestKafkaBrokerMetricHooks:
    def test_record_consumer_lag_calls_histogram(self) -> None:
        with patch("src.infrastructure.observability.metrics.broker_consumer_lag_messages") as m:
            KafkaMessageBroker._record_consumer_lag(
                topic="image.processing",
                partition=0,
                group="image-processing",
                lag=7,
            )
            m.record.assert_called_once_with(
                7,
                {"topic": "image.processing", "partition": "0", "group": "image-processing"},
            )

    def test_record_consumer_lag_swallows_error(self) -> None:
        with patch(
            "src.infrastructure.observability.metrics.broker_consumer_lag_messages",
            side_effect=RuntimeError("no OTel"),
        ):
            KafkaMessageBroker._record_consumer_lag(
                topic="image.processing",
                partition=1,
                group="image-processing",
                lag=2,
            )

    def test_record_consumer_rebalance_calls_counter(self) -> None:
        with patch("src.infrastructure.observability.metrics.broker_consumer_rebalances") as m:
            KafkaMessageBroker._record_consumer_rebalance(
                group="image-processing",
                event="assigned",
                partitions_count=2,
            )
            m.add.assert_called_once_with(
                1,
                {
                    "group": "image-processing",
                    "event": "assigned",
                    "partitions_count": "2",
                },
            )

    def test_record_consumer_rebalance_swallows_error(self) -> None:
        with patch(
            "src.infrastructure.observability.metrics.broker_consumer_rebalances",
            side_effect=RuntimeError("no OTel"),
        ):
            KafkaMessageBroker._record_consumer_rebalance(
                group="image-processing",
                event="revoked",
                partitions_count=3,
            )
