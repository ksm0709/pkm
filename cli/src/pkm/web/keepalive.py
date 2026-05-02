"""Keepalive helper used by SSE handlers (and tests).

Periodically invokes ``bump`` so that long-poll / SSE responses keep the
daemon's ``last_activity`` clock fresh and the idle_checker does not fire
mid-stream.
"""

from __future__ import annotations

import asyncio
from typing import Callable


async def run_keepalive(bump: Callable[[], None], interval: float = 30.0) -> None:
    """Loop forever, calling ``bump()`` every ``interval`` seconds.

    Cancelling the wrapping task is the only way to stop the loop; the caller
    is responsible for ``task.cancel(); await asyncio.gather(task, return_exceptions=True)``
    in their ``finally:`` block.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            bump()
        except Exception:
            # A failing bump must never tear down the SSE response.
            pass
