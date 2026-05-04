"""aiohttp application factory for the PKM web server."""

from __future__ import annotations

import logging
from importlib.resources import files
from pathlib import Path
from typing import Callable

from aiohttp import web

from pkm.config import WebConfig, get_web_config
from pkm.web.auth import logout, make_auth_middleware, make_login_handler
from pkm.web.app_keys import SEARCH_RUNNER_KEY
from pkm.web.routes import register_routes
from pkm.web.shutdown import ShutdownGate

_logger = logging.getLogger(__name__)


def _resolve_static_dir() -> Path | None:
    """Locate the bundled static asset directory inside the installed package.

    Returns *None* if the directory does not exist (dev install without a
    built frontend).
    """
    try:
        resource = files("pkm.web") / "static"
        path = Path(str(resource))
        if path.is_dir() and (path / "index.html").exists():
            return path
    except (ModuleNotFoundError, FileNotFoundError, TypeError):
        pass
    return None


def _make_spa_fallback(static_dir: Path) -> Callable:
    """Catch-all GET handler that serves the SPA index.html for non-API paths."""
    index_path = static_dir / "index.html"

    async def spa_fallback(request: web.Request) -> web.StreamResponse:
        rel = request.match_info.get("tail", "")
        if rel.startswith("api/"):
            raise web.HTTPNotFound()
        candidate = (static_dir / rel).resolve()
        try:
            candidate.relative_to(static_dir.resolve())
        except ValueError:
            raise web.HTTPNotFound()
        if candidate.is_file():
            return web.FileResponse(candidate)
        return web.FileResponse(index_path)

    return spa_fallback


async def _health_handler(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def make_app(
    gate: ShutdownGate | None = None,
    web_config: WebConfig | None = None,
    on_activity: Callable[[], None] | None = None,
    search_runner: Callable | None = None,
) -> web.Application:
    """Create and configure the aiohttp Application.

    Args:
        gate: ShutdownGate for drain tracking.  If *None*, drain is disabled.
        web_config: Web configuration; defaults to ``get_web_config()``.
        on_activity: Called on every authenticated request; use this to bump
            ``DaemonState.last_activity`` without creating a circular import.
        search_runner: Optional in-process semantic search callable for daemon-hosted web.
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
                    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, OPTIONS",
                    "Access-Control-Allow-Headers": "Authorization, Content-Type",
                    "Access-Control-Max-Age": "86400",
                },
            )
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = origin
        return response

    auth_mw = make_auth_middleware(cfg)

    app = web.Application(
        middlewares=[
            drain_middleware,
            activity_middleware,
            cors_middleware,
            auth_mw,
        ]
    )

    app.router.add_get("/api/v1/health", _health_handler)
    app.router.add_post("/api/v1/auth/login", make_login_handler(cfg))
    app.router.add_post("/api/v1/auth/logout", logout)
    if search_runner is not None:
        app[SEARCH_RUNNER_KEY] = search_runner
    register_routes(app)

    # Static asset serving (must be added AFTER api routes so api wins matching).
    static_dir = _resolve_static_dir()
    if static_dir is not None:
        app.router.add_get(
            "/{tail:(?!api/).*}",
            _make_spa_fallback(static_dir),
        )
    else:
        _logger.warning(
            "Static asset directory not found; frontend will not be served. "
            "Run `pnpm build` in web-frontend/ to populate cli/src/pkm/web/static/."
        )

    return app
