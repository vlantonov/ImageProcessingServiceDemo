"""Application configuration via pydantic-settings (12-factor compatible)."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Application ──────────────────────────────────────────────────────
    app_name: str = "image-processing-service"
    debug: bool = False

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/images"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ── Storage ──────────────────────────────────────────────────────────
    storage_base_dir: str = "/data/images"

    # ── Processing ───────────────────────────────────────────────────────
    processing_max_workers: int = 4
    thumbnail_max_size: int = 256

    # ── Retention ────────────────────────────────────────────────────────
    retention_batch_size: int = 100

    model_config = {"env_prefix": "IMG_"}
