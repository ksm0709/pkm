"""ShutdownGate: drain control and SSE cancel coordination for graceful restarts."""

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
        gate.cancel_all()                            # signal SSE streams to close
        await runner.cleanup()
        os.execv(...)

    Non-SSE handlers should wrap their work with::

        async with gate.track(request):
            ...
    """

    def __init__(self) -> None:
        self._draining: bool = False
        self._cancel_events: list[asyncio.Event] = []
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

    def register_cancel(self, event: asyncio.Event) -> None:
        """Register an asyncio.Event to be set when cancel_all() is called.

        Intended for SSE handlers that need to tear down their response
        stream on drain.
        """
        self._cancel_events.append(event)

    def cancel_all(self) -> None:
        """Set every registered SSE cancel event and clear the registry."""
        for event in self._cancel_events:
            event.set()
        self._cancel_events.clear()

    async def wait_idle(self) -> None:
        """Await until the in-flight non-SSE request counter reaches zero."""
        await self._idle_event.wait()

    @asynccontextmanager
    async def track(self, request: web.Request) -> AsyncGenerator[None, None]:
        """Async context manager: track one in-flight non-SSE request.

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
