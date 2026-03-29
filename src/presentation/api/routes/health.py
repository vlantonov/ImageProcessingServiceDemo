"""Health check endpoint for Kubernetes readiness/liveness probes."""

from __future__ import annotations

import importlib.metadata
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text

from src.config import Settings
from src.presentation.api.dependencies import _session_factory, get_settings
from src.presentation.schemas.image_schemas import ComponentCheck, HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_VERSION = importlib.metadata.version("image-processing-service")


async def _check_database() -> ComponentCheck:
    try:
        factory = _session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        return ComponentCheck(status="ok")
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return ComponentCheck(status="error", detail=str(exc))


def _check_storage(settings: Settings) -> ComponentCheck:
    storage_dir = Path(settings.storage_base_dir)
    if not storage_dir.is_dir():
        return ComponentCheck(status="error", detail="storage directory not found")
    return ComponentCheck(status="ok")


@router.get("/health", response_model=HealthResponse)
async def health_check(
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
):
    db = await _check_database()
    storage = _check_storage(settings)

    checks = {"database": db, "storage": storage}
    overall = "healthy" if all(c.status == "ok" for c in checks.values()) else "degraded"

    return HealthResponse(
        status=overall,
        service=settings.app_name,
        version=_VERSION,
        checks=checks,
    )
