"""Integration tests: auth middleware auth-split (B6).

Verifies:
- ?token= query param is rejected (401) on non-SSE routes.
- ?token= query param is accepted (200) on SSE-whitelisted routes.
- Authorization: Bearer header is accepted (200) on all routes.
"""

from __future__ import annotations

import pytest
from aiohttp import web as _web
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import WebConfig
from pkm.web.auth import SSE_ROUTES
from pkm.web.server import make_app

TOKEN = "test-bearer-token-b6-auth"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7420, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def app(web_cfg: WebConfig) -> _web.Application:
    """App with a stub /ask SSE route so the middleware can identify it."""
    a = make_app(web_config=web_cfg)

    async def _ask_stub(request: _web.Request) -> _web.Response:
        return _web.Response(text="ok")

    # Register with the same template that SSE_ROUTES lists so resource.canonical matches.
    a.router.add_get("/api/v1/vault/{name}/ask", _ask_stub)
    return a


@pytest.mark.anyio
async def test_query_token_rejected_on_non_sse_route(app: _web.Application) -> None:
    """`?token=` must return 401 on a regular (non-SSE) route."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v1/health", params={"token": TOKEN})
        assert resp.status == 401


@pytest.mark.anyio
async def test_query_token_accepted_on_sse_route(app: _web.Application) -> None:
    """`?token=` must return 200 on the SSE-whitelisted /ask route."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v1/vault/any-vault/ask", params={"token": TOKEN})
        assert resp.status == 200


@pytest.mark.anyio
async def test_bearer_header_accepted_on_non_sse_route(
    app: _web.Application,
) -> None:
    """`Authorization: Bearer` must work on any route."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/health", headers={"Authorization": f"Bearer {TOKEN}"}
        )
        assert resp.status == 200


@pytest.mark.anyio
async def test_bearer_header_accepted_on_sse_route(app: _web.Application) -> None:
    """`Authorization: Bearer` must also work on the SSE /ask route."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/any-vault/ask",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200


@pytest.mark.anyio
async def test_wrong_token_returns_401(app: _web.Application) -> None:
    """Wrong bearer token must return 401."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/health", headers={"Authorization": "Bearer wrong-token"}
        )
        assert resp.status == 401


def test_sse_routes_constant_contains_ask() -> None:
    """SSE_ROUTES must include the /ask path template."""
    assert any("ask" in route for route in SSE_ROUTES)
