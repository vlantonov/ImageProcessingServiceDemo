"""Concrete ImageStorage using the local file system.

In production this would be swapped for an S3-compatible or GCS adapter,
but the domain/application layers remain unchanged (Dependency Inversion).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from pathlib import Path

from src.domain.interfaces.image_storage import ImageStorage

logger = logging.getLogger(__name__)


class LocalImageStorage(ImageStorage):
    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    async def store(self, filename: str, data: bytes) -> str:
        content_hash = hashlib.sha256(data).hexdigest()[:12]
        # Use only the basename to strip any residual path components.
        basename = Path(filename).name or "unnamed"
        safe_name = f"{content_hash}_{basename}"
        dest = (self._base / safe_name).resolve()
        # Defence-in-depth: ensure the resolved path stays inside the base dir.
        if not str(dest).startswith(str(self._base.resolve())):
            raise ValueError("Path traversal detected in filename")
        await asyncio.to_thread(dest.write_bytes, data)
        logger.debug("Stored file: %s (%d bytes)", dest, len(data))
        return str(dest)

    async def retrieve(self, path: str) -> bytes:
        data = await asyncio.to_thread(Path(path).read_bytes)
        logger.debug("Retrieved file: %s (%d bytes)", path, len(data))
        return data

    async def delete(self, path: str) -> bool:
        try:
            await asyncio.to_thread(os.remove, path)
            logger.debug("Deleted file: %s", path)
            return True
        except FileNotFoundError:
            logger.debug("Delete skipped, file not found: %s", path)
            return False
