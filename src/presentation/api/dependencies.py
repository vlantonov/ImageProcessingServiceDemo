"""FastAPI dependency injection — wires infrastructure to use cases.

All concrete implementations are instantiated here, keeping route handlers
completely decoupled from infrastructure (Dependency Inversion Principle).
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from src.application.use_cases.apply_retention import ApplyRetentionUseCase
from src.application.use_cases.consume_processing_tasks import ConsumeProcessingTasksUseCase
from src.application.use_cases.get_image import GetImageUseCase
from src.application.use_cases.list_images import ListImagesUseCase
from src.application.use_cases.process_image import ProcessImageUseCase
from src.application.use_cases.upload_image import UploadImageUseCase
from src.config import Settings
from src.domain.interfaces.message_broker import MessageBroker
from src.infrastructure.cache.cached_image_repository import CachedImageRepository
from src.infrastructure.cache.in_memory_cache import InMemoryImageCache
from src.infrastructure.database.postgres_image_repository import PostgresImageRepository
from src.infrastructure.database.session import build_engine, build_session_factory
from src.infrastructure.processing.pillow_processor import PillowImageProcessor
from src.infrastructure.storage.local_image_storage import LocalImageStorage
from src.presentation.api.rate_limit import RateLimiter


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # pydantic-settings reads from env


_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    api_key: Annotated[str | None, Security(_api_key_header)] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> None:
    """Validate the X-API-Key header against the configured key.

    If IMG_API_KEY is not set (empty string), authentication is disabled.
    """
    configured_key = settings.api_key
    if not configured_key:
        return
    if api_key is None or not secrets.compare_digest(api_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


@lru_cache
def _session_factory():
    settings = get_settings()
    engine = build_engine(settings)
    return build_session_factory(engine)


@lru_cache
def _cache() -> InMemoryImageCache:
    settings = get_settings()
    return InMemoryImageCache(
        ttl_seconds=settings.cache_ttl_seconds,
        max_size=settings.cache_max_size,
    )


@lru_cache
def _repository() -> CachedImageRepository:
    return CachedImageRepository(
        inner=PostgresImageRepository(_session_factory()),
        cache=_cache(),
    )


@lru_cache
def _storage() -> LocalImageStorage:
    return LocalImageStorage(get_settings().storage_base_dir)


@lru_cache
def _processor() -> PillowImageProcessor:
    settings = get_settings()
    max_dim = settings.thumbnail_max_size
    return PillowImageProcessor(
        max_workers=settings.processing_max_workers,
        thumbnail_max_size=(max_dim, max_dim),
    )


@lru_cache
def _broker() -> MessageBroker | None:
    settings = get_settings()
    if not settings.broker_enabled:
        return None
    from src.infrastructure.messaging.kafka_message_broker import KafkaMessageBroker

    return KafkaMessageBroker(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        consumer_group=settings.kafka_consumer_group,
    )


_rate_limiters: dict[str, RateLimiter] = {}


def _get_rate_limiter(name: str, max_requests: int, window_seconds: int) -> RateLimiter:
    if name not in _rate_limiters:
        _rate_limiters[name] = RateLimiter(max_requests, window_seconds)
    return _rate_limiters[name]


async def upload_rate_limiter(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> None:
    limiter = _get_rate_limiter(
        "upload", settings.rate_limit_upload_max, settings.rate_limit_upload_window
    )
    await limiter(request)


async def process_rate_limiter(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> None:
    limiter = _get_rate_limiter(
        "process", settings.rate_limit_process_max, settings.rate_limit_process_window
    )
    await limiter(request)


async def read_rate_limiter(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> None:
    limiter = _get_rate_limiter(
        "read", settings.rate_limit_read_max, settings.rate_limit_read_window
    )
    await limiter(request)


def get_upload_use_case() -> UploadImageUseCase:
    return UploadImageUseCase(_repository(), _storage(), broker=_broker())


def get_process_use_case() -> ProcessImageUseCase:
    return ProcessImageUseCase(_repository(), _storage(), _processor())


def get_get_image_use_case() -> GetImageUseCase:
    return GetImageUseCase(_repository(), _storage())


def get_list_use_case() -> ListImagesUseCase:
    return ListImagesUseCase(_repository())


def get_retention_use_case() -> ApplyRetentionUseCase:
    return ApplyRetentionUseCase(_repository(), _storage())


def get_consume_use_case() -> ConsumeProcessingTasksUseCase:
    broker = _broker()
    if broker is None:
        from src.infrastructure.messaging.in_memory_message_broker import InMemoryMessageBroker

        broker = InMemoryMessageBroker()
    return ConsumeProcessingTasksUseCase(
        broker=broker,
        process_use_case=get_process_use_case(),
    )
