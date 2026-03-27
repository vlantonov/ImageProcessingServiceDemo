"""Retention management endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.use_cases.apply_retention import ApplyRetentionUseCase
from src.config import Settings
from src.presentation.api.dependencies import get_retention_use_case, get_settings
from src.presentation.schemas.image_schemas import RetentionResponse

router = APIRouter(prefix="/api/v1/retention", tags=["retention"])


@router.post("/sweep", response_model=RetentionResponse)
async def trigger_retention_sweep(
    use_case: Annotated[ApplyRetentionUseCase, Depends(get_retention_use_case)] = None,  # type: ignore[assignment]
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
):
    result = await use_case.execute(batch_size=settings.retention_batch_size)
    return RetentionResponse(deleted_count=result.deleted_count, errors=result.errors)
