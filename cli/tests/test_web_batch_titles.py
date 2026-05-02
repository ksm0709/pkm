"""Integration tests: POST /api/v1/vault/{name}/notes/batch-titles (B10b)."""

from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import VaultConfig, WebConfig
from pkm.web.server import make_app

TOKEN = "test-batch-titles-token-b10b"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7421, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def app(web_cfg: WebConfig):
    return make_app(web_config=web_cfg)


@pytest.mark.anyio
async def test_batch_titles_all_valid(app, tmp_vault: VaultConfig) -> None:
    """All IDs resolve to their titles."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/notes/batch-titles",
            json={"ids": ["2026-04-01-mvcc", "database-isolation"]},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "2026-04-01-mvcc" in data
        assert "database-isolation" in data
        # Titles should be non-empty strings
        assert data["2026-04-01-mvcc"] != ""
        assert data["database-isolation"] != ""


@pytest.mark.anyio
async def test_batch_titles_some_unresolved(app, tmp_vault: VaultConfig) -> None:
    """Unresolved IDs map to empty string."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/notes/batch-titles",
            json={"ids": ["2026-04-01-mvcc", "no-such-note-xyz"]},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["2026-04-01-mvcc"] != ""
        assert data["no-such-note-xyz"] == ""


@pytest.mark.anyio
async def test_batch_titles_auth_required(app, tmp_vault: VaultConfig) -> None:
    """Missing auth token returns 401."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/notes/batch-titles",
            json={"ids": ["2026-04-01-mvcc"]},
        )
        assert resp.status == 401


@pytest.mark.anyio
async def test_batch_titles_non_list_ids_returns_400(
    app, tmp_vault: VaultConfig
) -> None:
    """Non-list 'ids' field returns 400."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/notes/batch-titles",
            json={"ids": "not-a-list"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 400


@pytest.mark.anyio
async def test_batch_titles_too_many_ids_returns_400(
    app, tmp_vault: VaultConfig
) -> None:
    """More than 200 IDs returns 400."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/notes/batch-titles",
            json={"ids": [f"note-{i}" for i in range(201)]},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 400
