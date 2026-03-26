"""Health check endpoint for Kubernetes readiness/liveness probes."""

from __future__ import annotations

from fastapi import APIRouter

from src.presentation.schemas.image_schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        service="image-processing-service",
        version="1.0.0",
    )
