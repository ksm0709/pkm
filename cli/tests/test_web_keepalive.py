"""Scenario tests for web stream keepalive resilience."""

from __future__ import annotations

import asyncio

import pytest

from pkm.web.keepalive import run_keepalive


@pytest.mark.anyio
async def test_keepalive_continues_after_bump_failure() -> None:
    """A transient activity-bump failure must not tear down the stream task."""
    first_bump = asyncio.Event()
    second_bump = asyncio.Event()
    calls = 0

    def bump() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            first_bump.set()
            raise RuntimeError("activity update failed")
        second_bump.set()

    task = asyncio.create_task(run_keepalive(bump, interval=0.001))
    try:
        await asyncio.wait_for(first_bump.wait(), timeout=0.5)
        assert not task.done()

        await asyncio.wait_for(second_bump.wait(), timeout=0.5)
        assert calls >= 2
        assert not task.done()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
