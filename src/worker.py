"""Standalone Kafka consumer worker.

Run as a separate process to consume image-processing tasks from Kafka::

    python -m src.worker

In production, deploy multiple replicas behind the same consumer group
for horizontal scaling.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from src.application.use_cases.consume_processing_tasks import (
    IMAGE_PROCESSING_TOPIC,
    ConsumeProcessingTasksUseCase,
)
from src.application.use_cases.process_image import ProcessImageUseCase
from src.config import Settings
from src.infrastructure.cache.cached_image_repository import CachedImageRepository
from src.infrastructure.cache.in_memory_cache import InMemoryImageCache
from src.infrastructure.database.postgres_image_repository import PostgresImageRepository
from src.infrastructure.database.session import build_engine, build_session_factory
from src.infrastructure.messaging.kafka_message_broker import KafkaMessageBroker
from src.infrastructure.processing.pillow_processor import PillowImageProcessor
from src.infrastructure.storage.local_image_storage import LocalImageStorage
from src.presentation.logging_config import configure_logging

logger = logging.getLogger(__name__)

WORKER_METRICS_PORT = int(os.environ.get("IMG_WORKER_METRICS_PORT", "9090"))


def _setup_otel(settings: Settings) -> None:
    """Initialise OTel metrics so broker counters are exported via Prometheus."""
    otel_enabled = os.environ.get("IMG_OTEL_ENABLED", "").lower() in ("1", "true", "yes")
    if not otel_enabled:
        return
    from prometheus_client import start_http_server

    from src.infrastructure.observability.setup import setup_metrics

    service_name = os.environ.get("IMG_OTEL_SERVICE_NAME", "image-worker")
    setup_metrics(service_name=service_name)
    start_http_server(WORKER_METRICS_PORT)
    logger.info("Worker metrics server started on port %d", WORKER_METRICS_PORT)


async def run_worker() -> None:
    settings = Settings()  # type: ignore[call-arg]
    configure_logging(json_output=False)
    _setup_otel(settings)

    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    repository = CachedImageRepository(
        inner=PostgresImageRepository(session_factory),
        cache=InMemoryImageCache(
            ttl_seconds=settings.cache_ttl_seconds,
            max_size=settings.cache_max_size,
        ),
    )
    storage = LocalImageStorage(settings.storage_base_dir)
    max_dim = settings.thumbnail_max_size
    processor = PillowImageProcessor(
        max_workers=settings.processing_max_workers,
        thumbnail_max_size=(max_dim, max_dim),
    )

    broker = KafkaMessageBroker(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        consumer_group=settings.kafka_consumer_group,
        consumer_topics=[IMAGE_PROCESSING_TOPIC],
    )

    process_uc = ProcessImageUseCase(repository, storage, processor)
    consumer_uc = ConsumeProcessingTasksUseCase(broker, process_uc)

    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)

    logger.info(
        "Worker started — consuming from '%s' (group=%s)",
        IMAGE_PROCESSING_TOPIC,
        settings.kafka_consumer_group,
    )

    try:
        while not shutdown.is_set():
            await consumer_uc.execute_once()
    finally:
        await broker.close()
        from src.infrastructure.processing.pillow_processor import async_shutdown_executor

        await async_shutdown_executor()
        await engine.dispose()
        logger.info("Worker shut down cleanly")


if __name__ == "__main__":
    asyncio.run(run_worker())
