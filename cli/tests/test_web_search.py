"""Integration tests: GET /api/v1/vault/{name}/search (B10 / B11).

The route uses the same daemon-first search pipeline as ``pkm search``.
Tests monkeypatch the command module's imported search functions so no model
download is triggered.
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
    """Replace daemon, load_index, and search in the shared search pipeline."""
    from pkm import search_engine
    from pkm.commands import search as search_command

    def _load_index(vault):
        return object()

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

    monkeypatch.setattr(search_engine, "load_index", _load_index)
    monkeypatch.setattr(search_engine, "search", _fake_search)
    monkeypatch.setattr(search_command, "search_via_daemon", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(search_command, "load_index", _load_index)
    monkeypatch.setattr(search_command, "search_fn", _fake_search)
    return None


@pytest.mark.anyio
async def test_search_basic(app, tmp_vault: VaultConfig, patch_search) -> None:
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
async def test_search_empty_query_returns_400(app, tmp_vault: VaultConfig) -> None:
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
async def test_search_uses_the_same_daemon_first_pipeline_as_pkm_search_command(
    app, tmp_vault: VaultConfig, monkeypatch
) -> None:
    """Web search must reuse the pkm search command's daemon-first search path."""
    from pkm import search_engine
    from pkm.commands import search as search_command

    def _daemon_search(query, vault, top_n=10, **_kwargs):
        if query == "daemon-only":
            return [
                _FakeResult(
                    note_id="daemon-result",
                    title="Daemon Result",
                    score=0.99,
                    path="/nonexistent.md",
                )
            ]
        return None

    def _fail_load_index(_vault):
        raise AssertionError("web search should use daemon results before load_index")

    monkeypatch.setattr(search_engine, "search_via_daemon", _daemon_search)
    monkeypatch.setattr(search_engine, "load_index", _fail_load_index)
    monkeypatch.setattr(search_command, "search_via_daemon", _daemon_search)
    monkeypatch.setattr(search_command, "load_index", _fail_load_index)

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/search",
            params={"q": "daemon-only"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["query"] == "daemon-only"
        assert data["count"] == 1
        assert data["results"][0]["note_id"] == "daemon-result"


@pytest.mark.anyio
async def test_search_uses_injected_runner_without_command_pipeline(
    app, tmp_vault: VaultConfig, monkeypatch
) -> None:
    """Daemon-hosted web search must use the in-process runner, not socket RPC."""
    from pkm.commands import search as search_command
    from pkm.web.app_keys import SEARCH_RUNNER_KEY

    async def _runner(query, vault, top=10, **kwargs):
        assert query == "internal-only"
        assert vault.name == "test-vault"
        assert top == 3
        assert kwargs == {}
        return [
            _FakeResult(
                note_id="internal-result",
                title="Internal Result",
                score=0.88,
                path="/nonexistent.md",
            )
        ], "Index may be out of date. Run 'pkm index' to rebuild."

    def _unexpected_pipeline(*_args, **_kwargs):
        raise AssertionError("web search should not call daemon socket pipeline")

    app[SEARCH_RUNNER_KEY] = _runner
    monkeypatch.setattr(search_command, "run_search_pipeline", _unexpected_pipeline)

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/search",
            params={"q": "internal-only", "n": "3"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["query"] == "internal-only"
        assert data["count"] == 1
        assert data["results"][0]["note_id"] == "internal-result"
        assert "Index may be out of date" in data["warning"]


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
