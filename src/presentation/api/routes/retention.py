"""Retention management endpoint."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.use_cases.apply_retention import ApplyRetentionUseCase
from src.config import Settings
from src.presentation.api.dependencies import (
    get_retention_use_case,
    get_settings,
    process_rate_limiter,
    require_api_key,
)
from src.presentation.schemas.image_schemas import RetentionResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/retention",
    tags=["retention"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/sweep", response_model=RetentionResponse)
async def trigger_retention_sweep(
    use_case: Annotated[ApplyRetentionUseCase, Depends(get_retention_use_case)] = None,  # type: ignore[assignment]
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
    _rate: Annotated[None, Depends(process_rate_limiter())] = None,
):
    logger.info("Retention sweep triggered, batch_size=%d", settings.retention_batch_size)
    result = await use_case.execute(batch_size=settings.retention_batch_size)
    return RetentionResponse(deleted_count=result.deleted_count, errors=result.errors)
