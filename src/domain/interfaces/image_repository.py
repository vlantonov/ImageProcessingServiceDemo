"""Port: image metadata repository (database abstraction)."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from src.domain.entities.image import Image


class ImageRepository(ABC):
    """Abstract repository for persisting image metadata."""

    @abstractmethod
    async def save(self, image: Image) -> Image: ...

    @abstractmethod
    async def get_by_id(self, image_id: uuid.UUID) -> Image | None: ...

    @abstractmethod
    async def list_images(
        self, *, offset: int = 0, limit: int = 50, status: str | None = None
    ) -> list[Image]: ...

    @abstractmethod
    async def delete(self, image_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def get_expired(self, batch_size: int = 100) -> list[Image]: ...

    @abstractmethod
    async def delete_expired_batch(self, batch_size: int = 100) -> list[Image]:
        """Atomically select and delete expired images.

        Uses row-level locking so concurrent sweeps never process the
        same rows.  Returns the deleted entities (caller should clean
        up storage files afterward).
        """
        ...

    @abstractmethod
    async def count(self, *, status: str | None = None) -> int: ...
