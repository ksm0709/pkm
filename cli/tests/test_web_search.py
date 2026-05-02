"""Integration tests: GET /api/v1/vault/{name}/search (B10 / B11).

The route lazily imports ``pkm.search_engine.load_index`` and
``pkm.search_engine.search`` — both require sentence-transformers in
production.  Tests monkeypatch the module-level imports inside
``pkm.web.routes.search`` so no model download is triggered.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import VaultConfig, WebConfig
from pkm.web.server import make_app

TOKEN = "test-search-token-b11"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7431, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def app(web_cfg: WebConfig):
    return make_app(web_config=web_cfg)


@dataclass
class _FakeResult:
    note_id: str
    title: str
    score: float
    path: str
    memory_type: str = ""


@pytest.fixture
def patch_search(monkeypatch):
    """Replace load_index + search inside the search route module.

    The route does ``from pkm.search_engine import load_index, search as search_fn``
    *inside* the handler, so we monkeypatch on the source module.
    """
    from pkm import search_engine

    monkeypatch.setattr(search_engine, "load_index", lambda vault: object())

    def _fake_search(query, index, top_n=10, **_):
        if not query.strip() or query == "no-matches":
            return []
        # Return synthetic results referencing real notes from tmp_vault.
        return [
            _FakeResult(
                note_id="2026-04-01-mvcc",
                title="MVCC",
                score=0.91,
                path=str(_FakeResult.__module__),  # path is parsed best-effort
            ),
            _FakeResult(
                note_id="database-isolation",
                title="Database Isolation",
                score=0.78,
                path="/nonexistent.md",
            ),
        ]

    monkeypatch.setattr(search_engine, "search", _fake_search)
    return None


@pytest.mark.anyio
async def test_search_basic(
    app, tmp_vault: VaultConfig, patch_search
) -> None:
    """Basic query returns the expected envelope + non-empty results."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/search",
            params={"q": "mvcc"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["query"] == "mvcc"
        assert data["count"] == 2
        assert len(data["results"]) == 2
        first = data["results"][0]
        assert set(first.keys()) >= {"note_id", "title", "snippet", "score"}
        assert first["note_id"] == "2026-04-01-mvcc"


@pytest.mark.anyio
async def test_search_empty_query_returns_400(
    app, tmp_vault: VaultConfig
) -> None:
    """Empty/absent ``q`` must return 400."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/search",
            params={"q": ""},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 400

        resp = await client.get(
            "/api/v1/vault/test-vault/search",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 400


@pytest.mark.anyio
async def test_search_no_matches_returns_empty_list(
    app, tmp_vault: VaultConfig, patch_search
) -> None:
    """Query yielding no results returns count=0 / results=[]."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/search",
            params={"q": "no-matches"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["count"] == 0
        assert data["results"] == []


@pytest.mark.anyio
async def test_search_auth_required(app, tmp_vault: VaultConfig) -> None:
    """Missing token must return 401 (no body parsing required)."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/search",
            params={"q": "x"},
        )
        assert resp.status == 401
