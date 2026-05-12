"""Integration tests: POST /api/v1/vault/{name}/index."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer
from click import ClickException

from pkm.config import VaultConfig, WebConfig
from pkm.web.server import make_app

TOKEN = "test-index-token"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7441, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def app(web_cfg: WebConfig):
    return make_app(web_config=web_cfg)


@pytest.mark.anyio
async def test_index_vault_builds_index_and_graph(
    app, tmp_vault: VaultConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /index runs the same build_index helper as `pkm index`."""
    calls: list[VaultConfig] = []

    def fake_build_index(vault: VaultConfig):
        calls.append(vault)
        return SimpleNamespace(entries=[object(), object()])

    monkeypatch.setattr("pkm.search_engine.build_index", fake_build_index)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/index",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()

    assert calls == [tmp_vault]
    assert data["status"] == "ok"
    assert data["count"] == 2
    assert data["index_path"].endswith("/.pkm/index.json")
    assert data["graph_path"].endswith("/.pkm/graph.json")


@pytest.mark.anyio
async def test_index_vault_maps_search_dependency_errors_to_503(
    app, tmp_vault: VaultConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Optional search dependency failures should be visible to the web caller."""

    def missing_search_extra(_vault: VaultConfig):
        raise ClickException("sentence-transformers is not installed")

    monkeypatch.setattr("pkm.search_engine.build_index", missing_search_extra)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/index",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert resp.status == 503
    assert "sentence-transformers" in resp.reason


@pytest.mark.anyio
async def test_index_vault_requires_auth(app, tmp_vault: VaultConfig) -> None:
    """POST /index is a write-like expensive operation and requires auth."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/v1/vault/test-vault/index")

    assert resp.status == 401
