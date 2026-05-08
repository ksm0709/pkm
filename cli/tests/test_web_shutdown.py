"""Scenario tests for graceful web shutdown coordination."""

from __future__ import annotations

import asyncio

import pytest

from pkm.web.shutdown import ShutdownGate


@pytest.mark.anyio
async def test_wait_idle_returns_immediately_before_requests_are_tracked() -> None:
    """A fresh gate starts idle so shutdown does not wait on nonexistent work."""
    gate = ShutdownGate()

    await asyncio.wait_for(gate.wait_idle(), timeout=0.1)


@pytest.mark.anyio
async def test_wait_idle_releases_only_after_all_tracked_requests_exit() -> None:
    """Overlapping non-SSE requests keep drain waiting until the last one exits."""
    gate = ShutdownGate()

    async with gate.track(None):
        wait_task = asyncio.create_task(gate.wait_idle())
        await asyncio.sleep(0)
        assert not wait_task.done()

        async with gate.track(None):
            await asyncio.sleep(0)
            assert not wait_task.done()

        await asyncio.sleep(0)
        assert not wait_task.done()

    await asyncio.wait_for(wait_task, timeout=0.1)


@pytest.mark.anyio
async def test_track_releases_idle_waiters_after_handler_exception() -> None:
    """Request failures still decrement in-flight tracking and unblock shutdown."""
    gate = ShutdownGate()
    wait_task: asyncio.Task[None] | None = None

    with pytest.raises(RuntimeError, match="handler failed"):
        async with gate.track(None):
            wait_task = asyncio.create_task(gate.wait_idle())
            await asyncio.sleep(0)
            assert not wait_task.done()
            raise RuntimeError("handler failed")

    assert wait_task is not None
    await asyncio.wait_for(wait_task, timeout=0.1)
