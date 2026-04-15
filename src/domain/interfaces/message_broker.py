"""Port: message broker for event-driven processing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    """A message envelope for the processing queue."""

    topic: str
    key: str
    value: bytes


class MessageBroker(ABC):
    """Abstract broker for decoupling ingestion from processing."""

    @abstractmethod
    async def publish(self, message: Message) -> None:
        """Publish a message to the broker."""
        ...

    @abstractmethod
    async def consume(self, topic: str) -> Message | None:
        """Consume one message from the given topic.

        Returns ``None`` when no message is available (non-blocking).
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release broker resources."""
        ...
