"""Tests for pillow_processor async_shutdown_executor and executor lifecycle."""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
from unittest.mock import MagicMock, patch

from src.infrastructure.processing.pillow_processor import (
    async_shutdown_executor,
    get_executor,
    shutdown_executor,
)


class TestAsyncShutdownExecutor:
    async def test_shutdown_when_no_executor(self):
        """async_shutdown_executor does nothing when no executor exists."""
        import src.infrastructure.processing.pillow_processor as mod

        original = mod._executor
        mod._executor = None
        await async_shutdown_executor()
        # Should not raise
        mod._executor = original

    async def test_shutdown_normal(self):
        """async_shutdown_executor shuts down the executor cleanly."""
        import src.infrastructure.processing.pillow_processor as mod

        # Create a fresh executor
        mod._executor = ProcessPoolExecutor(max_workers=1)

        await async_shutdown_executor()

        assert mod._executor is None

    async def test_shutdown_timeout_forces_cancel(self):
        """When executor.shutdown takes too long, force-cancel is used."""
        import src.infrastructure.processing.pillow_processor as mod

        mock_executor = MagicMock(spec=ProcessPoolExecutor)

        # Make the shutdown hang
        async def _hanging_shutdown(*args, **kwargs):
            await asyncio.sleep(999)

        mod._executor = mock_executor

        with (
            patch.object(mod, "_SHUTDOWN_TIMEOUT_SECONDS", 0.01),
            patch("asyncio.get_running_loop") as mock_loop,
        ):
            loop = asyncio.get_running_loop()
            mock_loop.return_value = loop

            async def _slow_run(executor, fn, *args):
                await asyncio.sleep(999)

            with patch.object(loop, "run_in_executor", side_effect=_slow_run):
                await async_shutdown_executor()

        # After timeout, shutdown(wait=False, cancel_futures=True) should be called
        mock_executor.shutdown.assert_called_with(wait=False, cancel_futures=True)
        assert mod._executor is None


class TestGetExecutor:
    def test_get_executor_creates_singleton(self):
        import src.infrastructure.processing.pillow_processor as mod

        original = mod._executor
        mod._executor = None

        try:
            ex1 = get_executor(2)
            ex2 = get_executor(2)
            assert ex1 is ex2
        finally:
            if mod._executor is not None:
                mod._executor.shutdown(wait=False)
            mod._executor = original

    def test_shutdown_executor_clears_state(self):
        import src.infrastructure.processing.pillow_processor as mod

        original = mod._executor
        mod._executor = None

        try:
            get_executor(1)
            assert mod._executor is not None
            shutdown_executor()
            assert mod._executor is None
        finally:
            mod._executor = original
