"""Batch processing pipeline — processes multiple images concurrently.

Demonstrates asyncio.gather-based parallelism for high-throughput pipelines.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from src.application.use_cases.process_image import ProcessImageUseCase

logger = logging.getLogger(__name__)


async def process_batch(
    use_case: ProcessImageUseCase,
    image_ids: list[uuid.UUID],
    concurrency: int = 8,
) -> dict[str, int]:
    """Process a batch of images with bounded concurrency."""
    semaphore = asyncio.Semaphore(concurrency)
    success = 0
    failed = 0

    async def _process_one(image_id: uuid.UUID) -> bool:
        async with semaphore:
            return await use_case.execute(image_id)

    results = await asyncio.gather(
        *[_process_one(iid) for iid in image_ids],
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, BaseException):
            logger.error("Pipeline error: %s", result, exc_info=result)
            failed += 1
        elif result:
            success += 1
        else:
            failed += 1

    return {"success": success, "failed": failed}
