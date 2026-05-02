"""aiohttp application factory for the PKM web server."""

from __future__ import annotations

from typing import Callable

from aiohttp import web

from pkm.config import WebConfig, get_web_config
from pkm.web.auth import make_auth_middleware
from pkm.web.shutdown import ShutdownGate


async def _health_handler(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def make_app(
    gate: ShutdownGate | None = None,
    web_config: WebConfig | None = None,
    on_activity: Callable[[], None] | None = None,
) -> web.Application:
    """Create and configure the aiohttp Application.

    Args:
        gate: ShutdownGate for drain tracking.  If *None*, drain is disabled.
        web_config: Web configuration; defaults to ``get_web_config()``.
        on_activity: Called on every authenticated request; use this to bump
            ``DaemonState.last_activity`` without creating a circular import.
    """
    cfg = web_config or get_web_config()

    @web.middleware
    async def drain_middleware(
        request: web.Request,
        handler: Callable,
    ) -> web.StreamResponse:
        """Return 503 + Retry-After during graceful drain."""
        if gate is not None and gate.draining:
            return web.Response(
                status=503,
                text="Service draining, please retry shortly",
                headers={"Retry-After": "5"},
            )
        return await handler(request)

    @web.middleware
    async def activity_middleware(
        request: web.Request,
        handler: Callable,
    ) -> web.StreamResponse:
        """Bump last_activity on every incoming request."""
        if on_activity is not None:
            on_activity()
        return await handler(request)

    @web.middleware
    async def cors_middleware(
        request: web.Request,
        handler: Callable,
    ) -> web.StreamResponse:
        """Same-origin CORS: allow requests from the web server's own origin."""
        origin = f"http://localhost:{cfg.port}"
        if request.method == "OPTIONS":
            return web.Response(
                status=204,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Authorization, Content-Type",
                    "Access-Control-Max-Age": "86400",
                },
            )
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = origin
        return response

    auth_mw = make_auth_middleware(cfg.token_path)

    app = web.Application(
        middlewares=[
            drain_middleware,
            activity_middleware,
            cors_middleware,
            auth_mw,
        ]
    )

    app.router.add_get("/api/v1/health", _health_handler)

    return app
