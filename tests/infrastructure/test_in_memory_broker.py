"""Tests for the in-memory message broker."""

from __future__ import annotations

import pytest

from src.domain.interfaces.message_broker import Message
from src.infrastructure.messaging.in_memory_message_broker import InMemoryMessageBroker


@pytest.mark.asyncio
async def test_publish_and_consume():
    broker = InMemoryMessageBroker()
    msg = Message(topic="test-topic", key="k1", value=b'{"id": 1}')
    await broker.publish(msg)

    consumed = await broker.consume("test-topic")
    assert consumed is not None
    assert consumed.topic == "test-topic"
    assert consumed.key == "k1"
    assert consumed.value == b'{"id": 1}'


@pytest.mark.asyncio
async def test_consume_empty_returns_none():
    broker = InMemoryMessageBroker()
    result = await broker.consume("empty-topic")
    assert result is None


@pytest.mark.asyncio
async def test_multiple_messages_fifo():
    broker = InMemoryMessageBroker()
    await broker.publish(Message(topic="t", key="1", value=b"first"))
    await broker.publish(Message(topic="t", key="2", value=b"second"))

    first = await broker.consume("t")
    second = await broker.consume("t")
    assert first is not None
    assert first.value == b"first"
    assert second is not None
    assert second.value == b"second"


@pytest.mark.asyncio
async def test_close_clears_queues():
    broker = InMemoryMessageBroker()
    await broker.publish(Message(topic="t", key="1", value=b"data"))
    await broker.close()
    result = await broker.consume("t")
    assert result is None


@pytest.mark.asyncio
async def test_separate_topics():
    broker = InMemoryMessageBroker()
    await broker.publish(Message(topic="a", key="1", value=b"a-msg"))
    await broker.publish(Message(topic="b", key="1", value=b"b-msg"))

    a = await broker.consume("a")
    b = await broker.consume("b")
    assert a is not None and a.value == b"a-msg"
    assert b is not None and b.value == b"b-msg"
    assert await broker.consume("a") is None
