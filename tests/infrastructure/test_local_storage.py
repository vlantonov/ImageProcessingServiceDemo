"""Tests for the LocalImageStorage."""

from __future__ import annotations

import pytest

from src.infrastructure.storage.local_image_storage import LocalImageStorage


@pytest.fixture
def storage(tmp_path) -> LocalImageStorage:
    return LocalImageStorage(str(tmp_path / "images"))


@pytest.mark.asyncio
async def test_store_and_retrieve(storage):
    data = b"hello-image-bytes"
    path = await storage.store("test.png", data)

    assert path.endswith("test.png")
    retrieved = await storage.retrieve(path)
    assert retrieved == data


@pytest.mark.asyncio
async def test_delete(storage):
    path = await storage.store("del.png", b"delete-me")
    assert await storage.delete(path) is True
    assert await storage.delete(path) is False  # already gone


@pytest.mark.asyncio
async def test_store_unique_paths(storage):
    path1 = await storage.store("same.png", b"data-1")
    path2 = await storage.store("same.png", b"data-2")
    assert path1 != path2  # different content → different hash prefix
