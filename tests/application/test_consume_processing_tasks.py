"""Tests for the ConsumeProcessingTasks use case."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from src.application.use_cases.consume_processing_tasks import (
    IMAGE_PROCESSING_TOPIC,
    ConsumeProcessingTasksUseCase,
)
from src.domain.interfaces.message_broker import Message, MessageBroker


@pytest.fixture
def mock_broker() -> MessageBroker:
    return AsyncMock(spec=MessageBroker)


@pytest.fixture
def mock_process_uc() -> AsyncMock:
    uc = AsyncMock()
    uc.execute = AsyncMock(return_value=True)
    return uc


@pytest.mark.asyncio
async def test_execute_once_processes_message(mock_broker, mock_process_uc):
    image_id = uuid.uuid4()
    mock_broker.consume.return_value = Message(
        topic=IMAGE_PROCESSING_TOPIC,
        key=str(image_id),
        value=json.dumps({"image_id": str(image_id)}).encode(),
    )

    uc = ConsumeProcessingTasksUseCase(mock_broker, mock_process_uc)
    result = await uc.execute_once()

    assert result is True
    mock_broker.consume.assert_awaited_once_with(IMAGE_PROCESSING_TOPIC)
    mock_process_uc.execute.assert_awaited_once_with(image_id)


@pytest.mark.asyncio
async def test_execute_once_empty_queue(mock_broker, mock_process_uc):
    mock_broker.consume.return_value = None

    uc = ConsumeProcessingTasksUseCase(mock_broker, mock_process_uc)
    result = await uc.execute_once()

    assert result is False
    mock_process_uc.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_once_malformed_message(mock_broker, mock_process_uc):
    mock_broker.consume.return_value = Message(
        topic=IMAGE_PROCESSING_TOPIC,
        key="bad",
        value=b"not-json",
    )

    uc = ConsumeProcessingTasksUseCase(mock_broker, mock_process_uc)
    result = await uc.execute_once()

    assert result is True  # consumed but discarded
    mock_process_uc.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_once_missing_image_id(mock_broker, mock_process_uc):
    mock_broker.consume.return_value = Message(
        topic=IMAGE_PROCESSING_TOPIC,
        key="bad",
        value=json.dumps({"foo": "bar"}).encode(),
    )

    uc = ConsumeProcessingTasksUseCase(mock_broker, mock_process_uc)
    result = await uc.execute_once()

    assert result is True
    mock_process_uc.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_once_processing_failure_does_not_propagate(mock_broker, mock_process_uc):
    image_id = uuid.uuid4()
    mock_broker.consume.return_value = Message(
        topic=IMAGE_PROCESSING_TOPIC,
        key=str(image_id),
        value=json.dumps({"image_id": str(image_id)}).encode(),
    )
    mock_process_uc.execute.side_effect = RuntimeError("processing boom")

    uc = ConsumeProcessingTasksUseCase(mock_broker, mock_process_uc)
    result = await uc.execute_once()

    assert result is True
    mock_process_uc.execute.assert_awaited_once()
