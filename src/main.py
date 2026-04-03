"""FastAPI application factory — composes all layers."""

from __future__ import annotations

import asyncio
import importlib.metadata
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from src.presentation.api.dependencies import get_settings
from src.presentation.api.middleware import RequestLoggingMiddleware
from src.presentation.api.routes import health, images, retention
from src.presentation.logging_config import configure_logging


def _is_otel_enabled() -> bool:
    """Check OTel flag without requiring full Settings (DB creds may be absent)."""
    import os

    return os.getenv("IMG_OTEL_ENABLED", "false").lower() in ("1", "true", "yes")


def _is_cors_enabled() -> bool:
    """Check CORS origins without requiring full Settings (DB creds may be absent)."""
    import os

    return bool(os.getenv("IMG_CORS_ORIGINS", ""))


configure_logging(json_output=_is_otel_enabled())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run Alembic migrations on startup, clean up on shutdown."""
    from alembic import command
    from alembic.config import Config

    from src.infrastructure.database.session import build_engine

    settings = get_settings()
    engine = build_engine(settings)

    # ── OpenTelemetry SQLAlchemy + logging instrumentation ───────────────
    if _is_otel_enabled():
        from src.infrastructure.observability.setup import (
            instrument_logging,
            instrument_sqlalchemy,
        )

        instrument_sqlalchemy(engine.sync_engine)
        instrument_logging()
        logger.info("OpenTelemetry initialized")

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    logger.info("Database migrations applied")
    yield
    from src.infrastructure.processing.pillow_processor import shutdown_executor

    shutdown_executor()
    await engine.dispose()


def create_app() -> FastAPI:
    otel_enabled = _is_otel_enabled()

    # ── OpenTelemetry tracing/metrics must be set up before app creation ─
    if otel_enabled:
        from src.infrastructure.observability.setup import (
            instrument_app,
            setup_metrics,
            setup_tracing,
        )

        settings = get_settings()
        setup_tracing(
            service_name=settings.otel_service_name,
            otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        )
        setup_metrics(service_name=settings.otel_service_name)

    app = FastAPI(
        title="Image Processing Service",
        description="High-performance image processing microservice — Clean Architecture demo",
        version=importlib.metadata.version("image-processing-service"),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    if otel_enabled:
        from src.infrastructure.observability.middleware import MetricsMiddleware

        app.add_middleware(MetricsMiddleware)
        instrument_app(app)

    app.add_middleware(RequestLoggingMiddleware)

    if _is_cors_enabled():
        settings = get_settings()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=settings.cors_allow_methods,
            allow_headers=settings.cors_allow_headers,
        )

    app.include_router(health.router)
    app.include_router(images.router)
    app.include_router(retention.router)

    if otel_enabled:

        @app.get("/metrics", include_in_schema=False)
        async def metrics_endpoint() -> Response:
            from prometheus_client import generate_latest

            return Response(content=generate_latest(), media_type="text/plain; charset=utf-8")

    return app


app = create_app()
