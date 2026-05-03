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
from pkm.web.auth import (
    SESSION_COOKIE_NAME,
    SSE_ROUTES,
    hash_password,
)
from pkm.web.server import make_app

TOKEN = "test-bearer-token-b6-auth"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    password_path = tmp_path / "web-password"
    password_path.write_text(hash_password(PASSWORD), encoding="utf-8")
    return WebConfig(
        port=7420,
        bind="127.0.0.1",
        token_path=token_path,
        password_path=password_path,
        session_reset_path=tmp_path / "web-session-reset",
    )


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


@pytest.mark.anyio
async def test_password_login_sets_httponly_session_cookie(
    app: _web.Application,
) -> None:
    """Browser login uses a password and returns an HttpOnly session cookie."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"password": PASSWORD},
        )
        assert resp.status == 200
        cookie = resp.cookies[SESSION_COOKIE_NAME]
        assert cookie.value
        assert cookie["httponly"]
        assert cookie["samesite"] == "Lax"
        assert int(cookie["max-age"]) == 60 * 60 * 24 * 30


@pytest.mark.anyio
async def test_session_cookie_authenticates_regular_routes(
    app: _web.Application,
) -> None:
    """Session cookies authenticate browser REST requests without bearer token."""
    async with TestClient(TestServer(app)) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"password": PASSWORD},
        )
        assert login.status == 200

        resp = await client.get("/api/v1/health")
        assert resp.status == 200


@pytest.mark.anyio
async def test_wrong_password_returns_401_without_cookie(
    app: _web.Application,
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"password": "wrong"},
        )
        assert resp.status == 401
        assert SESSION_COOKIE_NAME not in resp.cookies


@pytest.mark.anyio
async def test_missing_password_config_fails_browser_login_closed(tmp_path) -> None:
    """Bearer auth can still work, but browser password login is disabled."""
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    app = make_app(
        web_config=WebConfig(
            port=7420,
            bind="127.0.0.1",
            token_path=token_path,
            password_path=tmp_path / "missing-password",
            session_reset_path=tmp_path / "web-session-reset",
        )
    )

    async with TestClient(TestServer(app)) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"password": PASSWORD},
        )
        assert login.status == 503

        bearer = await client.get(
            "/api/v1/health",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert bearer.status == 200


def test_sse_routes_constant_contains_ask() -> None:
    """SSE_ROUTES must include the /ask path template."""
    assert any("ask" in route for route in SSE_ROUTES)
