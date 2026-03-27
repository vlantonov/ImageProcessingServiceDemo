"""Image CRUD and processing routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status

from src.application.use_cases.get_image import GetImageUseCase
from src.application.use_cases.list_images import ListImagesUseCase
from src.application.use_cases.process_image import ProcessImageUseCase
from src.application.use_cases.upload_image import UploadImageUseCase
from src.infrastructure.processing.pipeline import process_batch
from src.presentation.api.dependencies import (
    get_get_image_use_case,
    get_list_use_case,
    get_process_use_case,
    get_upload_use_case,
)
from src.presentation.schemas.image_schemas import (
    BatchProcessRequest,
    BatchProcessResponse,
    ImageListOut,
    ImageOut,
)

router = APIRouter(prefix="/api/v1/images", tags=["images"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/tiff"}
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/", response_model=ImageOut, status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile,
    tags: Annotated[list[str], Query()] = [],
    ttl_hours: Annotated[int | None, Query(ge=1, le=8760)] = None,
    use_case: UploadImageUseCase = Depends(get_upload_use_case),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Content type {file.content_type} not supported",
        )
    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 50 MB limit",
        )
    result = await use_case.execute(
        filename=file.filename or "unnamed",
        data=data,
        tags=tags,
        ttl_hours=ttl_hours,
    )
    return result


@router.get("/", response_model=ImageListOut)
async def list_images(
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    use_case: ListImagesUseCase = Depends(get_list_use_case),
):
    return await use_case.execute(offset=offset, limit=limit, status=status_filter)


@router.get("/{image_id}", response_model=ImageOut)
async def get_image(
    image_id: uuid.UUID,
    use_case: GetImageUseCase = Depends(get_get_image_use_case),
):
    result = await use_case.execute(image_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return result


@router.get("/{image_id}/download")
async def download_image(
    image_id: uuid.UUID,
    thumbnail: bool = False,
    use_case: GetImageUseCase = Depends(get_get_image_use_case),
):
    data = await use_case.get_file(image_id, thumbnail=thumbnail)
    if data is None:
        raise HTTPException(status_code=404, detail="Image file not found")
    return Response(content=data, media_type="application/octet-stream")


@router.post("/batch/process", response_model=BatchProcessResponse)
async def process_batch_images(
    body: BatchProcessRequest,
    use_case: ProcessImageUseCase = Depends(get_process_use_case),
):
    result = await process_batch(use_case, body.image_ids, concurrency=body.concurrency)
    return result


@router.post("/{image_id}/process", response_model=ImageOut)
async def process_single_image(
    image_id: uuid.UUID,
    process_uc: ProcessImageUseCase = Depends(get_process_use_case),
    get_uc: GetImageUseCase = Depends(get_get_image_use_case),
):
    ok = await process_uc.execute(image_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Image not found")
    return await get_uc.execute(image_id)
