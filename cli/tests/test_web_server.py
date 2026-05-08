"""Scenario tests for PKM web application factory behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import pkm.web.server as server_mod
from pkm.config import WebConfig
from pkm.web.app_keys import SEARCH_RUNNER_KEY
from pkm.web.server import _make_spa_fallback, _resolve_static_dir, make_app
from pkm.web.shutdown import ShutdownGate

TOKEN = "test-server-token"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7444, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.mark.anyio
async def test_make_app_serves_static_asset_and_spa_fallback(
    tmp_path, web_cfg: WebConfig, auth_header, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bundled frontend assets serve files directly and SPA routes fall back to index."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<main>PKM App</main>", encoding="utf-8")
    (static_dir / "app.js").write_text("console.log('pkm')", encoding="utf-8")
    monkeypatch.setattr(server_mod, "_resolve_static_dir", lambda: static_dir)

    app = make_app(web_config=web_cfg)

    async with TestClient(TestServer(app)) as client:
        asset_resp = await client.get("/app.js", headers=auth_header)
        assert asset_resp.status == 200
        assert await asset_resp.text() == "console.log('pkm')"

        spa_resp = await client.get("/notes/2026-05-08", headers=auth_header)
        assert spa_resp.status == 200
        assert await spa_resp.text() == "<main>PKM App</main>"


@pytest.mark.anyio
@pytest.mark.parametrize("tail", ["api/v1/health", "../secret.txt"])
async def test_spa_fallback_rejects_api_and_traversal_paths(
    tmp_path, tail: str
) -> None:
    """The SPA fallback refuses API-looking paths and traversal outside static root."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("index", encoding="utf-8")
    handler = _make_spa_fallback(static_dir)
    request = SimpleNamespace(match_info={"tail": tail})

    with pytest.raises(web.HTTPNotFound):
        await handler(request)


@pytest.mark.anyio
async def test_drain_middleware_returns_retry_after(
    web_cfg: WebConfig, auth_header
) -> None:
    """A draining server rejects new requests with retry guidance before auth work."""
    gate = ShutdownGate()
    gate.begin_drain()
    app = make_app(web_config=web_cfg, gate=gate)

    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v1/health", headers=auth_header)
        assert resp.status == 503
        assert resp.headers["Retry-After"] == "5"
        assert "Service draining" in await resp.text()


@pytest.mark.anyio
async def test_cors_options_uses_configured_origin(web_cfg: WebConfig) -> None:
    """CORS preflight succeeds without auth and reflects the configured web origin."""
    app = make_app(web_config=web_cfg)

    async with TestClient(TestServer(app)) as client:
        resp = await client.options("/api/v1/health")
        assert resp.status == 204
        assert resp.headers["Access-Control-Allow-Origin"] == "http://localhost:7444"
        assert "PATCH" in resp.headers["Access-Control-Allow-Methods"]
        assert "Authorization" in resp.headers["Access-Control-Allow-Headers"]


@pytest.mark.anyio
async def test_activity_callback_and_search_runner_are_wired(
    web_cfg: WebConfig, auth_header
) -> None:
    """The app stores the in-process search runner and records request activity."""
    activity_count = 0

    def on_activity() -> None:
        nonlocal activity_count
        activity_count += 1

    async def search_runner(*_args, **_kwargs):
        return [], None

    app = make_app(
        web_config=web_cfg,
        on_activity=on_activity,
        search_runner=search_runner,
    )

    assert app[SEARCH_RUNNER_KEY] is search_runner
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v1/health", headers=auth_header)
        assert resp.status == 200
        assert await resp.json() == {"status": "ok"}

    assert activity_count == 1


def test_resolve_static_dir_returns_none_when_package_resource_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing bundled static resources disable frontend serving cleanly."""
    monkeypatch.setattr(
        server_mod,
        "files",
        lambda _package: (_ for _ in ()).throw(ModuleNotFoundError("missing")),
    )

    assert _resolve_static_dir() is None


@pytest.mark.anyio
async def test_make_app_defaults_to_get_web_config(
    tmp_path, auth_header, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When no config is passed, make_app uses get_web_config for middleware settings."""
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setattr(
        server_mod,
        "get_web_config",
        lambda: WebConfig(port=7555, bind="127.0.0.1", token_path=token_path),
    )

    app = make_app(web_config=None)

    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v1/health", headers=auth_header)
        assert resp.status == 200
        assert resp.headers["Access-Control-Allow-Origin"] == "http://localhost:7555"
