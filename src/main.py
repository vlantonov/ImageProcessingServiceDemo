"""FastAPI application factory — composes all layers."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.infrastructure.database.models import Base
from src.presentation.api.dependencies import get_settings
from src.presentation.api.middleware import RequestLoggingMiddleware
from src.presentation.api.routes import health, images, retention

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup (for demo/dev; use Alembic in production)."""
    from src.infrastructure.database.session import build_engine

    settings = get_settings()
    engine = build_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready")
    yield
    from src.infrastructure.processing.pillow_processor import shutdown_executor

    shutdown_executor()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Image Processing Service",
        description="High-performance image processing microservice — Clean Architecture demo",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(RequestLoggingMiddleware)

    app.include_router(health.router)
    app.include_router(images.router)
    app.include_router(retention.router)

    return app


app = create_app()
