"""Port: binary image storage (file system / object store abstraction)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ImageStorage(ABC):
    """Abstract storage backend for raw image files."""

    @abstractmethod
    async def store(self, filename: str, data: bytes) -> str:
        """Store image bytes; return the storage path/key."""
        ...

    @abstractmethod
    async def retrieve(self, path: str) -> bytes: ...

    @abstractmethod
    async def delete(self, path: str) -> bool: ...
