"""Integration tests: REST notes endpoints (B6).

Covers GET /api/v1/vaults, /api/v1/vault/{name}/notes,
/api/v1/vault/{name}/notes/{id}, and 404 paths.
"""

from __future__ import annotations

import json
import os
import time

import networkx as nx
import pytest
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import VaultConfig, WebConfig
from pkm.web.routes.notes import _note_description
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
        assert any(v["name"] == "test-vault" and v["is_default"] for v in data)


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
async def test_list_notes_sorts_newest_modified_first(
    app, tmp_vault: VaultConfig
) -> None:
    """The notes list should show recently modified notes first."""
    old_note = tmp_vault.notes_dir / "aaa-old-title.md"
    new_note = tmp_vault.notes_dir / "zzz-new-title.md"
    old_note.write_text(
        "---\nid: aaa-old-title\ntags: []\n---\n\nOld note.\n",
        encoding="utf-8",
    )
    new_note.write_text(
        "---\nid: zzz-new-title\ntags: []\n---\n\nNew note.\n",
        encoding="utf-8",
    )
    now = time.time()
    os.utime(old_note, (now - 1000, now - 1000))
    os.utime(new_note, (now, now))

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/notes",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()

    ids = [n["note_id"] for n in data]
    assert ids.index("zzz-new-title") < ids.index("aaa-old-title")
    assert data[0]["modified_at"]


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
            assert "modified_at" in item
            assert "description" in item


@pytest.mark.anyio
async def test_list_notes_includes_description_from_frontmatter(
    app, tmp_vault: VaultConfig
) -> None:
    """List summaries should include practical descriptions for the UI ledger."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/notes",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()

    by_id = {item["note_id"]: item for item in data}
    assert by_id["concurrency-note"]["description"] == (
        "Concurrency control technique comparison note"
    )
    assert by_id["database-isolation"]["description"].startswith(
        "Description of isolation levels."
    )


@pytest.mark.anyio
async def test_list_notes_skips_broken_markdown_file(
    app, tmp_vault: VaultConfig
) -> None:
    """A malformed note file must not break the whole notes listing."""
    (tmp_vault.notes_dir / "broken-frontmatter.md").write_text(
        "---\n: [bad\n---\nBroken note\n",
        encoding="utf-8",
    )

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/notes",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()

    note_ids = [item["note_id"] for item in data]
    assert "2026-04-01-mvcc" in note_ids
    assert "broken-frontmatter" not in note_ids


def test_note_description_fallback_skips_frontmatter() -> None:
    """Fallback descriptions must summarize note content, not metadata."""
    body = (
        "---\n"
        "id: metadata-heavy-note\n"
        "tags:\n"
        "  - TODO\n"
        "---\n\n"
        "Actual note content should be visible in the notes list.\n"
    )

    assert _note_description({}, body) == (
        "Actual note content should be visible in the notes list."
    )


def test_note_description_cleans_frontmatter_from_cached_description() -> None:
    """Cached graph/list descriptions can contain stale frontmatter artifacts."""
    raw_description = (
        "---\n"
        "id: cached-bad-description\n"
        "tags:\n"
        "  - TODO\n"
        "---\n\n"
        "Actual cached description should be visible.\n"
    )

    assert _note_description({"description": raw_description}) == (
        "Actual cached description should be visible."
    )


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
async def test_get_note_reads_daily_note_with_string_fields(
    app, tmp_vault: VaultConfig
) -> None:
    """Daily note IDs must render through the note route without JSON date errors."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/notes/2026-04-01",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["note_id"] == "2026-04-01"
        assert data["title"] == "2026-04-01"
        assert "Today task planning" in data["body"]


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
async def test_tag_neighbors_fall_back_to_inline_tag_scan_when_graph_is_stale(
    app, tmp_vault: VaultConfig
) -> None:
    """Tag pages must show tagged notes even when graph.json lacks that tag node."""
    (tmp_vault.daily_dir / "2026-04-30.md").write_text(
        "---\nid: 2026-04-30\naliases: []\ntags: []\n---\n\n"
        "- #TODO Follow up on stale graph fallback.\n",
        encoding="utf-8",
    )
    stale_graph = nx.DiGraph()
    stale_graph.add_node("unrelated", type="note", title="Unrelated")
    (tmp_vault.pkm_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(stale_graph)),
        encoding="utf-8",
    )

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/notes/tag:TODO/neighbors",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        inbound_ids = {item["note_id"] for item in data["inbound"]}
        assert "2026-04-30" in inbound_ids


@pytest.mark.anyio
async def test_unknown_vault_returns_404(app, tmp_vault: VaultConfig) -> None:
    """Request to an unknown vault must return 404."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/no-such-vault/notes",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 404
