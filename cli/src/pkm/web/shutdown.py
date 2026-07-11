"""ShutdownGate: drain control for graceful restarts."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from aiohttp import web


class ShutdownGate:
    """Coordinates graceful drain of in-flight HTTP requests on daemon restart.

    Typical usage (version-checker exec flow)::

        gate.begin_drain()                           # 503 all new requests
        await asyncio.wait_for(gate.wait_idle(), 5.0)  # wait up to 5 s
        await runner.cleanup()
        os.execv(...)

    Handlers should wrap their work with::

        async with gate.track(request):
            ...
    """

    def __init__(self) -> None:
        self._draining: bool = False
        self._in_flight: int = 0
        self._idle_event: asyncio.Event = asyncio.Event()
        self._idle_event.set()  # starts idle; cleared when first request is tracked

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def draining(self) -> bool:
        """True after begin_drain() has been called."""
        return self._draining

    def begin_drain(self) -> None:
        """Flip the draining flag.

        The auth/drain middleware should then return 503 + ``Retry-After: 5``
        for all new incoming requests.
        """
        self._draining = True

    async def wait_idle(self) -> None:
        """Await until the in-flight request counter reaches zero."""
        await self._idle_event.wait()

    @asynccontextmanager
    async def track(self, request: web.Request) -> AsyncGenerator[None, None]:
        """Async context manager: track one in-flight request.

        Increments the counter on entry and decrements on exit, setting the
        idle event when the counter returns to zero.
        """
        self._in_flight += 1
        self._idle_event.clear()
        try:
            yield
        finally:
            self._in_flight -= 1
            if self._in_flight <= 0:
                self._in_flight = 0
                self._idle_event.set()
