"""Tests for the ConsumeProcessingTasks use case."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from src.application.use_cases.consume_processing_tasks import (
    IMAGE_PROCESSING_DLQ_TOPIC,
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

    uc = ConsumeProcessingTasksUseCase(
        mock_broker,
        mock_process_uc,
        retry_max_attempts=0,
        retry_backoff_seconds=0.0,
    )
    result = await uc.execute_once()

    assert result is True
    mock_process_uc.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_once_processing_failure_retries_when_attempts_remaining(
    mock_broker, mock_process_uc
):
    image_id = uuid.uuid4()
    mock_broker.consume.return_value = Message(
        topic=IMAGE_PROCESSING_TOPIC,
        key=str(image_id),
        value=json.dumps({"image_id": str(image_id), "attempt": 0}).encode(),
    )
    mock_process_uc.execute.side_effect = RuntimeError("processing boom")

    uc = ConsumeProcessingTasksUseCase(
        mock_broker,
        mock_process_uc,
        retry_max_attempts=2,
        retry_backoff_seconds=0.0,
    )
    result = await uc.execute_once()

    assert result is True
    assert mock_broker.publish.await_count == 1
    retry_message = mock_broker.publish.await_args_list[0].args[0]
    assert retry_message.topic == IMAGE_PROCESSING_TOPIC
    assert json.loads(retry_message.value) == {"image_id": str(image_id), "attempt": 1}


@pytest.mark.asyncio
async def test_execute_once_processing_failure_routes_to_dlq_when_retries_exhausted(
    mock_broker, mock_process_uc
):
    image_id = uuid.uuid4()
    mock_broker.consume.return_value = Message(
        topic=IMAGE_PROCESSING_TOPIC,
        key=str(image_id),
        value=json.dumps({"image_id": str(image_id), "attempt": 2}).encode(),
    )
    mock_process_uc.execute.side_effect = RuntimeError("processing boom")

    uc = ConsumeProcessingTasksUseCase(
        mock_broker,
        mock_process_uc,
        retry_max_attempts=2,
        retry_backoff_seconds=0.0,
    )
    result = await uc.execute_once()

    assert result is True
    assert mock_broker.publish.await_count == 1
    dlq_message = mock_broker.publish.await_args_list[0].args[0]
    assert dlq_message.topic == IMAGE_PROCESSING_DLQ_TOPIC
    assert json.loads(dlq_message.value)["reason"] == "retries_exhausted"


@pytest.mark.asyncio
async def test_execute_once_malformed_message_routes_to_dlq(mock_broker, mock_process_uc):
    mock_broker.consume.return_value = Message(
        topic=IMAGE_PROCESSING_TOPIC,
        key="bad-key",
        value=b"not-json",
    )

    uc = ConsumeProcessingTasksUseCase(mock_broker, mock_process_uc, retry_backoff_seconds=0.0)
    result = await uc.execute_once()

    assert result is True
    assert mock_broker.publish.await_count == 1
    dlq_message = mock_broker.publish.await_args_list[0].args[0]
    assert dlq_message.topic == IMAGE_PROCESSING_DLQ_TOPIC
    assert json.loads(dlq_message.value)["reason"] == "malformed"
