"""aiohttp authentication middleware for the PKM web server.

Canonical auth for all routes: Authorization: Bearer <token> header.
?token= query param is only honoured on SSE routes (EventSource cannot
send custom headers).
"""
from __future__ import annotations

import hmac
from functools import lru_cache
from pathlib import Path
from typing import Awaitable, Callable

from aiohttp import web

# Routes where ?token= query param is accepted as a fallback (SSE only).
# Matched against the request's matched-route *template* (resource canonical),
# not the raw URL, so path variables do not interfere.
SSE_ROUTES: frozenset[str] = frozenset({"/api/v1/vault/{vault}/ask"})


def _load_token(token_path: Path) -> str:
    """Read and strip the bearer token from *token_path*.

    Called once per process (cached).  Raises RuntimeError if the file is
    missing or empty so the server fails fast on misconfiguration.
    """
    if not token_path.exists():
        raise RuntimeError(
            f"Web token file not found: {token_path}. "
            "Generate one with: pkm web token --generate"
        )
    token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError(f"Web token file is empty: {token_path}")
    return token


def make_auth_middleware(token_path: Path) -> web.middleware:
    """Return an aiohttp middleware factory bound to *token_path*.

    The token file is read exactly once (on first authenticated request) and
    cached for the lifetime of the process.
    """

    @lru_cache(maxsize=1)
    def _get_token() -> str:
        return _load_token(token_path)

    @web.middleware
    async def auth_middleware(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        """Authenticate every incoming request.

        Precedence:
        1. ``Authorization: Bearer <token>`` header  — valid on all routes.
        2. ``?token=<token>`` query param             — valid ONLY on SSE routes.
        """
        expected = _get_token()

        # --- Bearer header (canonical, accepted everywhere) ---
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            provided = auth_header[len("Bearer "):]
            if hmac.compare_digest(provided, expected):
                return await handler(request)
            return web.Response(status=401, text="Invalid token")

        # --- ?token= query param (SSE routes only) ---
        resource = request.match_info.route.resource
        route_template: str = resource.canonical if resource is not None else ""

        if route_template in SSE_ROUTES:
            provided = request.rel_url.query.get("token", "")
            if provided and hmac.compare_digest(provided, expected):
                return await handler(request)

        return web.Response(
            status=401,
            text="Unauthorized",
            headers={"WWW-Authenticate": 'Bearer realm="pkm"'},
        )

    return auth_middleware
