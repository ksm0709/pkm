"""Slice-1 honesty test: long-poll vs idle_checker (B6a).

xfail(strict=True): currently fails — last_activity is bumped only at request
entry, so the idle_checker fires during the poll.

Once B9 SSE keepalive lands in slice 3, the keepalive helper periodically
refreshes last_activity, the assertion passes, and the xfail marker must be
removed (strict=True causes a suite failure on unexpected pass, forcing cleanup).

Production mapping: _POLL_SLEEP ≈ 70 s, _IDLE_TIMEOUT ≈ 60 s.
The test uses scaled-down values to keep CI fast while proving identical logic.
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import VaultConfig, WebConfig
from pkm.web.server import make_app

TOKEN = "test-longpoll-b6a"

# Scaled-down stand-ins for production values.
_POLL_SLEEP = 0.8  # production: 70 s — handler sleeps this long
_IDLE_TIMEOUT = 0.5  # production: 60 s — idle_checker fires after this


@pytest.mark.anyio
@pytest.mark.xfail(
    strict=True,
    reason="will pass after B9 SSE keepalive lands in slice 3",
)
async def test_long_poll_activity_stays_fresh(
    tmp_vault: VaultConfig,
    tmp_path,
    monkeypatch,
) -> None:
    """last_activity must remain fresh throughout a long poll (requires B9 keepalive).

    The idle_checker fires when ``monotonic() - last_activity > idle_timeout``.
    With only an entry-time bump, last_activity becomes stale for the full poll
    duration.  After B9, a keepalive helper periodically refreshes it so the
    idle_checker never fires during an active poll.

    Assertion: at the moment the idle_checker fires (after idle_timeout), the
    age of last_activity must be less than idle_timeout/2.

    - Currently FAILS: age ≈ idle_timeout (bumped once at entry, never refreshed).
    - After B9: keepalive refreshes last_activity → age << idle_timeout → PASSES.
    """
    # Gate: expose the test route only under PKM_TEST=1 (never in production).
    monkeypatch.setenv("PKM_TEST", "1")

    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    web_cfg = WebConfig(port=7421, bind="127.0.0.1", token_path=token_path)
    app = make_app(web_config=web_cfg)

    # Shared mutable state: handler writes, checker reads.
    last_activity: list[float] = [time.monotonic()]

    async def long_poll_handler(request: web.Request) -> web.Response:
        """Temporary test route: bump last_activity once at entry, then hold open."""
        last_activity[0] = time.monotonic()  # entry-only bump (no keepalive yet)
        await asyncio.sleep(_POLL_SLEEP)
        return web.Response(text="ok")

    if os.environ.get("PKM_TEST") == "1":
        app.router.add_get("/api/v1/_test/long_poll", long_poll_handler)

    async def _idle_checker() -> float:
        """Simulate idle_checker: sleep idle_timeout, return last_activity age."""
        await asyncio.sleep(_IDLE_TIMEOUT)
        return time.monotonic() - last_activity[0]

    async with TestClient(TestServer(app)) as client:
        checker_task = asyncio.create_task(_idle_checker())
        request_task = asyncio.create_task(
            client.get(
                "/api/v1/_test/long_poll",
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
        )

        age_at_idle_timeout = await checker_task

        # ASSERTION (currently fails — xfail):
        # last_activity must be refreshed within idle_timeout/2 by the keepalive.
        # Without B9: age ≈ _IDLE_TIMEOUT → fails.
        # With B9 keepalive: age << _IDLE_TIMEOUT → passes.
        freshness_threshold = _IDLE_TIMEOUT / 2
        assert age_at_idle_timeout < freshness_threshold, (
            f"last_activity is {age_at_idle_timeout:.3f}s stale when idle_checker fires "
            f"(threshold: {freshness_threshold:.3f}s); "
            "entry-only bump insufficient — keepalive required (B9)"
        )

        request_task.cancel()
        try:
            await request_task
        except (asyncio.CancelledError, Exception):
            pass
