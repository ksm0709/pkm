"""Integration tests: neighbors endpoint with SEMANTIC group assertion (B6).

Key assertion: SEMANTIC group is populated when graph_enriched.json contains
semantic_similar edges for the requested note.

This also serves as a regression test for the include_semantic=True requirement:
if the route ever forgets to pass include_semantic=True to
_get_note_neighbors_data, the SEMANTIC group will be empty and these tests fail.
"""

from __future__ import annotations

import json

import networkx as nx
import pytest
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import VaultConfig, WebConfig
from pkm.web.server import make_app

TOKEN = "test-neighbors-token-b6"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7420, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def vault_with_graphs(tmp_vault: VaultConfig) -> VaultConfig:
    """Extend tmp_vault with graph.json + graph_enriched.json.

    graph.json: mvcc → database-isolation (structural directed edge)
    graph_enriched.json: mvcc — database-isolation (semantic_similar, confidence=0.92)
    """
    # Structural directed graph
    G = nx.DiGraph()
    G.add_node("2026-04-01-mvcc", title="MVCC", type="note")
    G.add_node("database-isolation", title="Database Isolation", type="note")
    G.add_edge("2026-04-01-mvcc", "database-isolation")
    (tmp_vault.pkm_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(G)), encoding="utf-8"
    )

    # Enriched graph with semantic_similar edge
    EG = nx.Graph()
    EG.add_node("2026-04-01-mvcc", title="MVCC", type="note")
    EG.add_node("database-isolation", title="Database Isolation", type="note")
    EG.add_edge(
        "2026-04-01-mvcc",
        "database-isolation",
        type="semantic_similar",
        confidence=0.92,
    )
    (tmp_vault.pkm_dir / "graph_enriched.json").write_text(
        json.dumps(nx.node_link_data(EG)), encoding="utf-8"
    )
    return tmp_vault


@pytest.mark.anyio
async def test_semantic_group_populated(
    web_cfg: WebConfig, vault_with_graphs: VaultConfig
) -> None:
    """SEMANTIC group must be non-empty when graph_enriched.json has semantic edges."""
    app = make_app(web_config=web_cfg)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/notes/2026-04-01-mvcc/neighbors",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "semantic" in data
        assert len(data["semantic"]) > 0, (
            "SEMANTIC group is empty — route likely missing include_semantic=True"
        )
        semantic_ids = [n["note_id"] for n in data["semantic"]]
        assert "database-isolation" in semantic_ids


@pytest.mark.anyio
async def test_neighbors_structure(
    web_cfg: WebConfig, vault_with_graphs: VaultConfig
) -> None:
    """Response must include outbound, inbound, and semantic top-level keys."""
    app = make_app(web_config=web_cfg)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/notes/2026-04-01-mvcc/neighbors",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert set(data.keys()) >= {"note_id", "outbound", "inbound", "semantic"}
        # mvcc has an outbound edge to database-isolation
        assert len(data["outbound"]) > 0


@pytest.mark.anyio
async def test_neighbors_no_graph_returns_404(
    web_cfg: WebConfig, tmp_vault: VaultConfig
) -> None:
    """Should return 404 when graph.json does not exist."""
    app = make_app(web_config=web_cfg)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/notes/2026-04-01-mvcc/neighbors",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 404
