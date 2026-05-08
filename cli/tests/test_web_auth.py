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
    SESSION_MAX_AGE_SECONDS,
    SSE_ROUTES,
    _load_token,
    create_session_cookie_value,
    hash_password,
    make_auth_middleware,
    verify_password,
    verify_session_cookie_value,
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
async def test_pwa_install_assets_are_public_without_auth(
    web_cfg: WebConfig,
) -> None:
    """Browser install checks fetch PWA assets without app auth headers."""
    app = _web.Application(middlewares=[make_auth_middleware(web_cfg)])

    async def _asset_stub(request: _web.Request) -> _web.Response:
        return _web.Response(text="asset-ok")

    app.router.add_get("/manifest.webmanifest", _asset_stub)
    app.router.add_get("/service-worker.js", _asset_stub)
    app.router.add_get("/icons/{name}", _asset_stub)

    async with TestClient(TestServer(app)) as client:
        for path in (
            "/manifest.webmanifest",
            "/service-worker.js",
            "/icons/pwa-192.png",
            "/icons/pwa-512.png",
        ):
            resp = await client.get(path)
            assert resp.status == 200, path
            assert await resp.text() == "asset-ok"


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
async def test_login_rejects_malformed_json(app: _web.Application) -> None:
    """Malformed login bodies are client errors, not invalid-password attempts."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/auth/login",
            data="{",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400


@pytest.mark.anyio
async def test_logout_clears_browser_session_cookie(app: _web.Application) -> None:
    """Logout is public and instructs the browser to clear the session cookie."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/v1/auth/logout")
        assert resp.status == 200
        assert await resp.json() == {"ok": True}

    cookie = resp.cookies[SESSION_COOKIE_NAME]
    assert cookie.value == ""
    assert cookie["path"] == "/"


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


def test_load_token_fails_fast_for_missing_or_empty_token_file(tmp_path) -> None:
    """Server token misconfiguration is reported before accepting protected traffic."""
    missing = tmp_path / "missing-token"
    with pytest.raises(RuntimeError, match="Generate one with: pkm setup --web"):
        _load_token(missing)

    empty = tmp_path / "empty-token"
    empty.write_text("\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="is empty"):
        _load_token(empty)


def test_password_verifier_rejects_unknown_or_malformed_hashes() -> None:
    """Password hashes fail closed when the stored format is not trusted."""
    good_hash = hash_password(PASSWORD, salt=b"0" * 16)
    _, iterations, salt, digest = good_hash.split("$", 3)

    assert not verify_password(PASSWORD, f"argon2${iterations}${salt}${digest}")
    assert not verify_password(PASSWORD, "not-a-valid-password-hash")


def test_session_cookie_verifier_rejects_malformed_or_out_of_window_tokens() -> None:
    """Session cookies are bound to format, signature inputs, and max age."""
    password_hash = hash_password(PASSWORD, salt=b"1" * 16)
    cookie = create_session_cookie_value(
        token=TOKEN,
        password_hash=password_hash,
        reset_value="",
        now=1_000,
    )
    assert verify_session_cookie_value(
        cookie,
        token=TOKEN,
        password_hash=password_hash,
        reset_value="",
        now=1_000,
    )

    assert not verify_session_cookie_value(
        cookie.replace("v1$", "v2$", 1),
        token=TOKEN,
        password_hash=password_hash,
        now=1_000,
    )
    assert not verify_session_cookie_value(
        "v1$1000$$bad-signature",
        token=TOKEN,
        password_hash=password_hash,
        now=1_000,
    )
    assert not verify_session_cookie_value(
        "not-a-cookie",
        token=TOKEN,
        password_hash=password_hash,
        now=1_000,
    )

    future_cookie = create_session_cookie_value(
        token=TOKEN,
        password_hash=password_hash,
        now=2_000,
    )
    assert not verify_session_cookie_value(
        future_cookie,
        token=TOKEN,
        password_hash=password_hash,
        now=1_000,
    )

    expired_cookie = create_session_cookie_value(
        token=TOKEN,
        password_hash=password_hash,
        now=1_000,
    )
    assert not verify_session_cookie_value(
        expired_cookie,
        token=TOKEN,
        password_hash=password_hash,
        now=1_000 + SESSION_MAX_AGE_SECONDS + 1,
    )


@pytest.mark.anyio
async def test_session_cookie_is_rejected_after_reset_file_changes(
    app: _web.Application, web_cfg: WebConfig
) -> None:
    """Writing the reset file invalidates existing browser sessions."""
    async with TestClient(TestServer(app)) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"password": PASSWORD},
        )
        assert login.status == 200

        web_cfg.session_reset_path.write_text("reset-now", encoding="utf-8")
        resp = await client.get("/api/v1/health")
        assert resp.status == 401
