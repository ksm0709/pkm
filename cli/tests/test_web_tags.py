"""Integration tests: tags routes (B10 / B11)."""

from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import VaultConfig, WebConfig
from pkm.web.server import make_app

TOKEN = "test-tags-token-b11"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7432, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def app(web_cfg: WebConfig):
    return make_app(web_config=web_cfg)


@pytest.mark.anyio
async def test_list_tags_returns_pairs(app, tmp_vault: VaultConfig) -> None:
    """GET /tags returns a sorted list of {tag, count} pairs."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/tags",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "tags" in data and "count" in data
        tag_names = {item["tag"] for item in data["tags"]}
        # tmp_vault fixture seeds these tags.
        assert "database" in tag_names
        assert "daily-notes" in tag_names
        for item in data["tags"]:
            assert "tag" in item
            assert isinstance(item["count"], int)
            assert item["count"] >= 1
        assert data["count"] == len(data["tags"])


@pytest.mark.anyio
async def test_search_tags_exact(app, tmp_vault: VaultConfig) -> None:
    """Exact-match pattern returns only notes carrying that tag."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/tags/search",
            params={"pattern": "postgresql"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["pattern"] == "postgresql"
        assert data["mode"].startswith("exact(")
        ids = [r["note_id"] for r in data["results"]]
        assert "2026-04-01-mvcc" in ids


@pytest.mark.anyio
async def test_search_tags_glob(app, tmp_vault: VaultConfig) -> None:
    """Glob pattern uses ``glob`` mode."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/tags/search",
            params={"pattern": "data*"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["mode"].startswith("glob(")
        # mvcc, database-isolation, concurrency-note all carry tag "database".
        ids = {r["note_id"] for r in data["results"]}
        assert "2026-04-01-mvcc" in ids
        assert "database-isolation" in ids


@pytest.mark.anyio
async def test_tags_routes_include_inline_body_tags(
    app, tmp_vault: VaultConfig
) -> None:
    """Body hashtags are first-class tags for tag lists and tag search."""
    (tmp_vault.notes_dir / "inline-todo.md").write_text(
        "---\nid: inline-todo\naliases: []\ntags: []\n---\n\n"
        "This note is tracked with #TODO in the content.\n",
        encoding="utf-8",
    )

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/tags",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        tag_counts = {item["tag"]: item["count"] for item in data["tags"]}
        assert tag_counts["TODO"] == 1

        resp = await client.get(
            "/api/v1/vault/test-vault/tags/search",
            params={"pattern": "TODO"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        ids = {r["note_id"] for r in data["results"]}
        assert "inline-todo" in ids


@pytest.mark.anyio
async def test_search_tags_serializes_daily_note_date_titles(
    app, tmp_vault: VaultConfig
) -> None:
    """Daily-note date titles must not make tag search return HTTP 500."""
    (tmp_vault.daily_dir / "2026-04-30.md").write_text(
        "---\nid: 2026-04-30\naliases: []\ntags: []\n---\n\n"
        "- #TODO Follow up.\n",
        encoding="utf-8",
    )

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/tags/search",
            params={"pattern": "TODO"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        first = data["results"][0]
        assert first["note_id"] == "2026-04-30"
        assert first["title"] == "2026-04-30"


@pytest.mark.anyio
async def test_search_tags_empty_pattern_returns_400(
    app, tmp_vault: VaultConfig
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/tags/search",
            params={"pattern": ""},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 400


@pytest.mark.anyio
async def test_tags_auth_required(app, tmp_vault: VaultConfig) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v1/vault/test-vault/tags")
        assert resp.status == 401

        resp = await client.get(
            "/api/v1/vault/test-vault/tags/search", params={"pattern": "x"}
        )
        assert resp.status == 401
