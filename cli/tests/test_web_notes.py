"""Integration tests: REST notes endpoints (B6).

Covers GET /api/v1/vaults, /api/v1/vault/{name}/notes,
/api/v1/vault/{name}/notes/{id}, and 404 paths.
"""

from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import VaultConfig, WebConfig
from pkm.web.server import make_app

TOKEN = "test-notes-token-b6"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7420, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def app(web_cfg: WebConfig):
    return make_app(web_config=web_cfg)


@pytest.mark.anyio
async def test_get_vaults_returns_list(app, tmp_vault: VaultConfig) -> None:
    """GET /api/v1/vaults returns a list including the test vault."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vaults", headers={"Authorization": f"Bearer {TOKEN}"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert isinstance(data, list)
        assert any(v["name"] == "test-vault" for v in data)


@pytest.mark.anyio
async def test_list_notes_returns_notes(app, tmp_vault: VaultConfig) -> None:
    """GET /api/v1/vault/{name}/notes returns a non-empty list of note summaries."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/notes",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        note_ids = [n["note_id"] for n in data]
        assert "2026-04-01-mvcc" in note_ids


@pytest.mark.anyio
async def test_list_notes_items_have_required_keys(app, tmp_vault: VaultConfig) -> None:
    """Each item in the list response must have the expected summary keys."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/notes",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        for item in data:
            assert "note_id" in item
            assert "title" in item
            assert "tags" in item


@pytest.mark.anyio
async def test_get_note_returns_8_keys(app, tmp_vault: VaultConfig) -> None:
    """GET /api/v1/vault/{name}/notes/{id} returns all 8 required keys."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/notes/2026-04-01-mvcc",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert set(data.keys()) >= {
            "note_id",
            "title",
            "body",
            "frontmatter",
            "created",
            "updated",
            "tags",
            "importance",
        }
        assert data["note_id"] == "2026-04-01-mvcc"


@pytest.mark.anyio
async def test_get_note_not_found_returns_404(app, tmp_vault: VaultConfig) -> None:
    """Non-existent note must return 404."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/notes/does-not-exist",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 404


@pytest.mark.anyio
async def test_unknown_vault_returns_404(app, tmp_vault: VaultConfig) -> None:
    """Request to an unknown vault must return 404."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/no-such-vault/notes",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 404
