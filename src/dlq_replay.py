"""Replay helper for Kafka dead-letter messages.

Usage::

    python -m src.dlq_replay --limit 100
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer  # type: ignore[import-untyped]

from src.application.use_cases.consume_processing_tasks import IMAGE_PROCESSING_TOPIC
from src.config import Settings
from src.presentation.logging_config import configure_logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplayMessage:
    key: str
    value: bytes


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay image-processing DLQ messages.")
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum DLQ records to inspect in one run (default: 100).",
    )
    parser.add_argument(
        "--source-topic",
        default=None,
        help="DLQ topic to read from (default: IMG_KAFKA_DLQ_TOPIC).",
    )
    parser.add_argument(
        "--target-topic",
        default=IMAGE_PROCESSING_TOPIC,
        help=f"Topic to replay to (default: {IMAGE_PROCESSING_TOPIC}).",
    )
    parser.add_argument(
        "--consumer-group",
        default=None,
        help="Consumer group for replay reader (default: <IMG_KAFKA_CONSUMER_GROUP>-dlq-replay).",
    )
    parser.add_argument(
        "--poll-timeout-ms",
        type=int,
        default=1_000,
        help="Poll timeout in milliseconds before exiting when idle (default: 1000).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and validate DLQ messages without publishing or committing offsets.",
    )
    return parser.parse_args()


def _parse_dlq_payload(raw_value: bytes) -> dict[str, Any]:
    payload = json.loads(raw_value)
    if not isinstance(payload, dict):
        raise ValueError("DLQ payload must be a JSON object")
    return payload


def _build_replay_message(payload: Mapping[str, Any]) -> ReplayMessage:
    embedded_payload = payload.get("payload")
    if isinstance(embedded_payload, Mapping):
        image_id = embedded_payload.get("image_id")
        if image_id is not None:
            replay_payload = {"image_id": str(image_id), "attempt": 0}
            return ReplayMessage(
                key=str(payload.get("original_key") or image_id),
                value=json.dumps(replay_payload).encode(),
            )

    original_value = payload.get("original_value")
    if not isinstance(original_value, str):
        raise ValueError("DLQ payload is missing both 'payload.image_id' and 'original_value'")

    parsed_original_value = json.loads(original_value)
    if not isinstance(parsed_original_value, dict) or "image_id" not in parsed_original_value:
        raise ValueError("original_value does not contain a replayable image_id")

    replay_payload = {"image_id": str(parsed_original_value["image_id"]), "attempt": 0}
    replay_key = str(payload.get("original_key") or replay_payload["image_id"])
    return ReplayMessage(key=replay_key, value=json.dumps(replay_payload).encode())


async def _run_replay(args: argparse.Namespace) -> None:
    settings = Settings()  # type: ignore[call-arg]
    source_topic = args.source_topic or settings.kafka_dlq_topic
    consumer_group = args.consumer_group or f"{settings.kafka_consumer_group}-dlq-replay"

    consumer = AIOKafkaConsumer(
        source_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=consumer_group,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)

    inspected = 0
    replayed = 0
    skipped = 0

    await consumer.start()
    if not args.dry_run:
        await producer.start()

    logger.info(
        "Starting DLQ replay: source=%s target=%s limit=%d dry_run=%s group=%s",
        source_topic,
        args.target_topic,
        args.limit,
        args.dry_run,
        consumer_group,
    )
    try:
        while inspected < args.limit:
            remaining = args.limit - inspected
            batches = await consumer.getmany(timeout_ms=args.poll_timeout_ms, max_records=remaining)
            if not batches:
                logger.info("No more DLQ messages available, exiting.")
                break

            batch_count = 0
            for records in batches.values():
                for record in records:
                    batch_count += 1
                    inspected += 1

                    try:
                        dlq_payload = _parse_dlq_payload(record.value)
                        replay_message = _build_replay_message(dlq_payload)
                    except (json.JSONDecodeError, ValueError) as exc:
                        skipped += 1
                        logger.error(
                            "Skipping non-replayable DLQ message (offset=%d): %s",
                            record.offset,
                            exc,
                        )
                        continue

                    if args.dry_run:
                        logger.info(
                            "Dry-run replay candidate key=%s offset=%d",
                            replay_message.key,
                            record.offset,
                        )
                        continue

                    await producer.send_and_wait(
                        args.target_topic,
                        key=replay_message.key.encode(),
                        value=replay_message.value,
                    )
                    replayed += 1

            if not args.dry_run and batch_count > 0:
                await consumer.commit()

    finally:
        await consumer.stop()
        if not args.dry_run:
            await producer.stop()

    logger.info(
        "DLQ replay finished: inspected=%d replayed=%d skipped=%d dry_run=%s",
        inspected,
        replayed,
        skipped,
        args.dry_run,
    )


def main() -> None:
    configure_logging(json_output=False)
    args = _parse_args()
    if args.limit < 1:
        raise ValueError("--limit must be >= 1")
    if args.poll_timeout_ms < 1:
        raise ValueError("--poll-timeout-ms must be >= 1")
    asyncio.run(_run_replay(args))


if __name__ == "__main__":
    main()
