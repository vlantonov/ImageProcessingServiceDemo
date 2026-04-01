"""Edge-case tests: API-level failures, timeouts, and error propagation."""

from __future__ import annotations

import contextlib
import io
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage

from src.application.dto.image_dto import ImageListResponse, ImageResponse
from src.application.use_cases.apply_retention import ApplyRetentionUseCase, RetentionResult
from src.application.use_cases.get_image import GetImageUseCase
from src.application.use_cases.list_images import ListImagesUseCase
from src.application.use_cases.process_image import ProcessImageUseCase
from src.application.use_cases.upload_image import UploadImageUseCase
from src.config import Settings
from src.main import app
from src.presentation.api.dependencies import (
    get_get_image_use_case,
    get_list_use_case,
    get_process_use_case,
    get_retention_use_case,
    get_settings,
    get_upload_use_case,
)
from src.presentation.schemas.image_schemas import ComponentCheck


@pytest.fixture
def image_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def image_response(image_id) -> ImageResponse:
    return ImageResponse(
        id=image_id,
        filename="test.png",
        status="completed",
        width=100,
        height=80,
        format="PNG",
        size_bytes=1024,
        tags=["test"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        expires_at=None,
        thumbnail_available=True,
    )


@pytest.fixture
def png_upload_bytes() -> bytes:
    img = PILImage.new("RGB", (50, 50), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@contextlib.contextmanager
def make_client(
    *,
    mock_upload=None,
    mock_get=None,
    mock_list=None,
    mock_process=None,
    mock_retention=None,
    tmp_path=None,
):
    @asynccontextmanager
    async def _noop_lifespan(a):
        yield

    app.router.lifespan_context = _noop_lifespan

    if mock_upload:
        app.dependency_overrides[get_upload_use_case] = lambda: mock_upload
    if mock_get:
        app.dependency_overrides[get_get_image_use_case] = lambda: mock_get
    if mock_list:
        app.dependency_overrides[get_list_use_case] = lambda: mock_list
    if mock_process:
        app.dependency_overrides[get_process_use_case] = lambda: mock_process
    if mock_retention:
        app.dependency_overrides[get_retention_use_case] = lambda: mock_retention

    test_settings = Settings(
        storage_base_dir=str(tmp_path) if tmp_path else "/tmp/test",
        db_user="test",
        db_password="test",
    )
    app.dependency_overrides[get_settings] = lambda: test_settings

    async def _ok_db_check():
        return ComponentCheck(status="ok")

    with patch("src.presentation.api.routes.health._check_database", side_effect=_ok_db_check):
        yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()


# ── Upload failure edge cases ────────────────────────────────────────────────


class TestUploadEdgeCases:
    @pytest.fixture
    def client(self, image_response, tmp_path):
        mock_upload = AsyncMock(spec=UploadImageUseCase)
        mock_upload.execute = AsyncMock(return_value=image_response)
        with make_client(mock_upload=mock_upload, tmp_path=tmp_path) as c:
            yield c

    def test_upload_zero_byte_file(self, client):
        """Empty file upload should be rejected by image validation."""
        resp = client.post(
            "/api/v1/images/",
            files={"file": ("empty.png", b"", "image/png")},
        )
        assert resp.status_code == 422
        assert "validation failed" in resp.json()["detail"].lower()

    def test_upload_non_image_content_as_png(self, client):
        """File with image content type but non-image data should fail validation."""
        resp = client.post(
            "/api/v1/images/",
            files={"file": ("fake.png", b"this is plain text", "image/png")},
        )
        assert resp.status_code == 422

    def test_upload_bmp_content_type_rejected(self, client):
        """BMP content type is not in the allowed list."""
        img = PILImage.new("RGB", (10, 10))
        buf = io.BytesIO()
        img.save(buf, format="BMP")
        resp = client.post(
            "/api/v1/images/",
            files={"file": ("test.bmp", buf.getvalue(), "image/bmp")},
        )
        assert resp.status_code == 415

    def test_upload_with_exactly_max_tags(self, client, png_upload_bytes):
        """Exactly 20 tags should be accepted."""
        tags = [f"tag{i}" for i in range(20)]
        resp = client.post(
            "/api/v1/images/",
            files={"file": ("test.png", png_upload_bytes, "image/png")},
            params={"tags": tags},
        )
        assert resp.status_code == 201

    def test_upload_use_case_internal_error(self, tmp_path, png_upload_bytes):
        """Internal error from use case should return 500."""
        mock_upload = AsyncMock(spec=UploadImageUseCase)
        mock_upload.execute = AsyncMock(side_effect=RuntimeError("DB exploded"))
        with make_client(mock_upload=mock_upload, tmp_path=tmp_path) as client:
            resp = client.post(
                "/api/v1/images/",
                files={"file": ("test.png", png_upload_bytes, "image/png")},
            )
            assert resp.status_code == 500


# ── Get / Download failure edge cases ────────────────────────────────────────


class TestGetDownloadEdgeCases:
    def test_get_nonexistent_image(self, tmp_path):
        mock_get = AsyncMock(spec=GetImageUseCase)
        mock_get.execute = AsyncMock(return_value=None)
        mock_get.get_file = AsyncMock(return_value=None)
        with make_client(mock_get=mock_get, tmp_path=tmp_path) as client:
            resp = client.get(f"/api/v1/images/{uuid.uuid4()}")
            assert resp.status_code == 404

    def test_download_nonexistent_image(self, tmp_path):
        mock_get = AsyncMock(spec=GetImageUseCase)
        mock_get.execute = AsyncMock(return_value=None)
        mock_get.get_file = AsyncMock(return_value=None)
        with make_client(mock_get=mock_get, tmp_path=tmp_path) as client:
            resp = client.get(f"/api/v1/images/{uuid.uuid4()}/download")
            assert resp.status_code == 404

    def test_download_thumbnail_not_available(self, tmp_path):
        mock_get = AsyncMock(spec=GetImageUseCase)
        mock_get.get_file = AsyncMock(return_value=None)
        with make_client(mock_get=mock_get, tmp_path=tmp_path) as client:
            resp = client.get(f"/api/v1/images/{uuid.uuid4()}/download?thumbnail=true")
            assert resp.status_code == 404

    def test_get_with_invalid_uuid_format(self, tmp_path):
        mock_get = AsyncMock(spec=GetImageUseCase)
        with make_client(mock_get=mock_get, tmp_path=tmp_path) as client:
            resp = client.get("/api/v1/images/not-a-uuid")
            assert resp.status_code == 422


# ── Process failure edge cases ───────────────────────────────────────────────


class TestProcessEdgeCases:
    def test_process_nonexistent_image(self, image_response, tmp_path):
        mock_process = AsyncMock(spec=ProcessImageUseCase)
        mock_process.execute = AsyncMock(return_value=False)
        mock_get = AsyncMock(spec=GetImageUseCase)
        mock_get.execute = AsyncMock(return_value=image_response)
        with make_client(mock_process=mock_process, mock_get=mock_get, tmp_path=tmp_path) as client:
            resp = client.post(f"/api/v1/images/{uuid.uuid4()}/process")
            assert resp.status_code == 404

    def test_process_internal_error(self, tmp_path):
        mock_process = AsyncMock(spec=ProcessImageUseCase)
        mock_process.execute = AsyncMock(side_effect=RuntimeError("Processing failed"))
        mock_get = AsyncMock(spec=GetImageUseCase)
        with make_client(mock_process=mock_process, mock_get=mock_get, tmp_path=tmp_path) as client:
            resp = client.post(f"/api/v1/images/{uuid.uuid4()}/process")
            assert resp.status_code == 500


# ── List images edge cases ───────────────────────────────────────────────────


class TestListEdgeCases:
    def test_list_negative_offset_rejected(self, tmp_path):
        mock_list = AsyncMock(spec=ListImagesUseCase)
        with make_client(mock_list=mock_list, tmp_path=tmp_path) as client:
            resp = client.get("/api/v1/images/?offset=-1")
            assert resp.status_code == 422

    def test_list_limit_zero_rejected(self, tmp_path):
        mock_list = AsyncMock(spec=ListImagesUseCase)
        with make_client(mock_list=mock_list, tmp_path=tmp_path) as client:
            resp = client.get("/api/v1/images/?limit=0")
            assert resp.status_code == 422

    def test_list_limit_exceeds_max_rejected(self, tmp_path):
        mock_list = AsyncMock(spec=ListImagesUseCase)
        with make_client(mock_list=mock_list, tmp_path=tmp_path) as client:
            resp = client.get("/api/v1/images/?limit=101")
            assert resp.status_code == 422

    def test_list_empty_result(self, tmp_path):
        mock_list = AsyncMock(spec=ListImagesUseCase)
        mock_list.execute = AsyncMock(
            return_value=ImageListResponse(images=[], total=0, offset=0, limit=50)
        )
        with make_client(mock_list=mock_list, tmp_path=tmp_path) as client:
            resp = client.get("/api/v1/images/")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 0
            assert data["images"] == []


# ── Retention endpoint edge cases ────────────────────────────────────────────


class TestRetentionEdgeCases:
    def test_retention_sweep_with_errors(self, tmp_path):
        mock_retention = AsyncMock(spec=ApplyRetentionUseCase)
        mock_retention.execute = AsyncMock(return_value=RetentionResult(deleted_count=5, errors=2))
        with make_client(mock_retention=mock_retention, tmp_path=tmp_path) as client:
            resp = client.post("/api/v1/retention/sweep")
            assert resp.status_code == 200
            data = resp.json()
            assert data["deleted_count"] == 5
            assert data["errors"] == 2

    def test_retention_sweep_internal_error(self, tmp_path):
        mock_retention = AsyncMock(spec=ApplyRetentionUseCase)
        mock_retention.execute = AsyncMock(side_effect=RuntimeError("DB deadlock"))
        with make_client(mock_retention=mock_retention, tmp_path=tmp_path) as client:
            resp = client.post("/api/v1/retention/sweep")
            assert resp.status_code == 500
