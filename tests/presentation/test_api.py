"""Integration tests for the FastAPI endpoints.

Uses dependency override to inject mocks — no real DB or storage needed.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage

from src.application.dto.image_dto import ImageListResponse, ImageResponse
from src.application.use_cases.get_image import GetImageUseCase
from src.application.use_cases.list_images import ListImagesUseCase
from src.application.use_cases.process_image import ProcessImageUseCase
from src.application.use_cases.upload_image import UploadImageUseCase
from src.main import app
from src.presentation.api.dependencies import (
    get_get_image_use_case,
    get_list_use_case,
    get_process_use_case,
    get_upload_use_case,
)


@pytest.fixture
def image_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def image_response(image_id) -> ImageResponse:
    return ImageResponse(
        id=image_id,
        filename="test.png",
        status="pending",
        width=None,
        height=None,
        format=None,
        size_bytes=None,
        tags=["test"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        expires_at=None,
        thumbnail_available=False,
    )


@pytest.fixture
def png_upload_bytes() -> bytes:
    img = PILImage.new("RGB", (50, 50), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def client(image_response) -> TestClient:
    from contextlib import asynccontextmanager

    # Override lifespan to skip DB connection in tests
    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    app.router.lifespan_context = _noop_lifespan

    mock_upload = AsyncMock(spec=UploadImageUseCase)
    mock_upload.execute = AsyncMock(return_value=image_response)

    mock_get = AsyncMock(spec=GetImageUseCase)
    mock_get.execute = AsyncMock(return_value=image_response)
    mock_get.get_file = AsyncMock(return_value=b"file-bytes")

    mock_list = AsyncMock(spec=ListImagesUseCase)
    mock_list.execute = AsyncMock(
        return_value=ImageListResponse(images=[image_response], total=1, offset=0, limit=50)
    )

    mock_process = AsyncMock(spec=ProcessImageUseCase)
    mock_process.execute = AsyncMock(return_value=True)

    app.dependency_overrides[get_upload_use_case] = lambda: mock_upload
    app.dependency_overrides[get_get_image_use_case] = lambda: mock_get
    app.dependency_overrides[get_list_use_case] = lambda: mock_list
    app.dependency_overrides[get_process_use_case] = lambda: mock_process

    yield TestClient(app)

    app.dependency_overrides.clear()


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "image-processing-service"


class TestImageUpload:
    def test_upload_success(self, client, png_upload_bytes):
        resp = client.post(
            "/api/v1/images/",
            files={"file": ("test.png", png_upload_bytes, "image/png")},
            params={"tags": ["test"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["filename"] == "test.png"

    def test_upload_invalid_content_type(self, client):
        resp = client.post(
            "/api/v1/images/",
            files={"file": ("doc.pdf", b"not-an-image", "application/pdf")},
        )
        assert resp.status_code == 415

    def test_upload_too_many_tags(self, client, png_upload_bytes):
        tags = [f"tag{i}" for i in range(21)]
        resp = client.post(
            "/api/v1/images/",
            files={"file": ("test.png", png_upload_bytes, "image/png")},
            params={"tags": tags},
        )
        assert resp.status_code == 422


class TestImageList:
    def test_list_images(self, client):
        resp = client.get("/api/v1/images/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["images"]) == 1


class TestImageGet:
    def test_get_image(self, client, image_id):
        resp = client.get(f"/api/v1/images/{image_id}")
        assert resp.status_code == 200

    def test_download_image(self, client, image_id):
        resp = client.get(f"/api/v1/images/{image_id}/download")
        assert resp.status_code == 200
        assert resp.content == b"file-bytes"
