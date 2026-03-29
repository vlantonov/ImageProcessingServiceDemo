"""FastAPI dependency injection — wires infrastructure to use cases.

All concrete implementations are instantiated here, keeping route handlers
completely decoupled from infrastructure (Dependency Inversion Principle).
"""

from __future__ import annotations

from functools import lru_cache

from src.application.use_cases.apply_retention import ApplyRetentionUseCase
from src.application.use_cases.get_image import GetImageUseCase
from src.application.use_cases.list_images import ListImagesUseCase
from src.application.use_cases.process_image import ProcessImageUseCase
from src.application.use_cases.upload_image import UploadImageUseCase
from src.config import Settings
from src.infrastructure.cache.cached_image_repository import CachedImageRepository
from src.infrastructure.cache.in_memory_cache import InMemoryImageCache
from src.infrastructure.database.postgres_image_repository import PostgresImageRepository
from src.infrastructure.database.session import build_engine, build_session_factory
from src.infrastructure.processing.pillow_processor import PillowImageProcessor
from src.infrastructure.storage.local_image_storage import LocalImageStorage


@lru_cache
def get_settings() -> Settings:
    return Settings()


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
    return PillowImageProcessor(max_workers=get_settings().processing_max_workers)


def get_upload_use_case() -> UploadImageUseCase:
    return UploadImageUseCase(_repository(), _storage())


def get_process_use_case() -> ProcessImageUseCase:
    return ProcessImageUseCase(_repository(), _storage(), _processor())


def get_get_image_use_case() -> GetImageUseCase:
    return GetImageUseCase(_repository(), _storage())


def get_list_use_case() -> ListImagesUseCase:
    return ListImagesUseCase(_repository())


def get_retention_use_case() -> ApplyRetentionUseCase:
    return ApplyRetentionUseCase(_repository(), _storage())
