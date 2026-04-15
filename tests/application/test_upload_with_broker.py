"""Tests for upload → broker event publishing integration."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.application.use_cases.upload_image import UploadImageUseCase
from src.domain.interfaces.message_broker import MessageBroker


@pytest.mark.asyncio
async def test_upload_publishes_processing_event(mock_repository, mock_storage):
    mock_repository.save.side_effect = lambda img: img
    broker = AsyncMock(spec=MessageBroker)

    uc = UploadImageUseCase(mock_repository, mock_storage, broker=broker)
    result = await uc.execute(filename="cat.png", data=b"img-data", tags=["cat"])

    broker.publish.assert_awaited_once()
    msg = broker.publish.call_args[0][0]
    assert msg.topic == "image.processing"
    payload = json.loads(msg.value)
    assert payload["image_id"] == str(result.id)


@pytest.mark.asyncio
async def test_upload_without_broker_does_not_publish(mock_repository, mock_storage):
    mock_repository.save.side_effect = lambda img: img

    uc = UploadImageUseCase(mock_repository, mock_storage)
    result = await uc.execute(filename="cat.png", data=b"img-data")

    assert result.filename == "cat.png"
    # No exception — broker is None, publish not called
