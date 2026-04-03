"""Application configuration via pydantic-settings (12-factor compatible)."""

from __future__ import annotations

from urllib.parse import quote_plus

from pydantic import computed_field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Application ──────────────────────────────────────────────────────
    app_name: str = "image-processing-service"
    debug: bool = False

    # ── Database ─────────────────────────────────────────────────────────
    # Credentials MUST be supplied via environment variables or a secrets
    # manager; no defaults are provided to prevent accidental leakage.
    db_user: str  # required — no default
    db_password: str  # required — no default
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "images"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        password = quote_plus(self.db_password)
        return (
            f"postgresql+asyncpg://{self.db_user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    # ── Storage ──────────────────────────────────────────────────────────
    storage_base_dir: str = "/data/images"

    # ── Processing ───────────────────────────────────────────────────────
    processing_max_workers: int = 4
    thumbnail_max_size: int = 256

    # ── Cache ─────────────────────────────────────────────────────────
    cache_ttl_seconds: int = 60
    cache_max_size: int = 1024

    # ── Retention ────────────────────────────────────────────────────────
    retention_batch_size: int = 100

    # ── Rate Limiting ────────────────────────────────────────────────────
    rate_limit_upload_max: int = 10
    rate_limit_upload_window: int = 60
    rate_limit_process_max: int = 20
    rate_limit_process_window: int = 60
    rate_limit_read_max: int = 60
    rate_limit_read_window: int = 60

    # ── Authentication ───────────────────────────────────────────────────
    api_key: str = ""

    # ── CORS ─────────────────────────────────────────────────────────────
    cors_origins: list[str] = []
    cors_allow_methods: list[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    cors_allow_headers: list[str] = ["*"]

    # ── Observability ────────────────────────────────────────────────────
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "image-processing-service"

    model_config = {"env_prefix": "IMG_"}
