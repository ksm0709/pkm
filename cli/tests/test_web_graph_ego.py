"""Integration tests for vault graph REST routes."""

from __future__ import annotations

import json

import networkx as nx
import pytest
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import VaultConfig, WebConfig
from pkm.web.server import make_app

TOKEN = "test-graph-ego-token-b11"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7433, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def app(web_cfg: WebConfig):
    return make_app(web_config=web_cfg)


@pytest.fixture
def vault_with_graph(tmp_vault: VaultConfig) -> VaultConfig:
    """Three-node directed chain A → B → C, plus a disconnected island D."""
    G = nx.DiGraph()
    G.add_node("a", title="A", type="note")
    G.add_node("b", title="B", type="note")
    G.add_node("c", title="C", type="note")
    G.add_node("d", title="D (island)", type="note")
    G.add_edge("a", "b")
    G.add_edge("b", "c")
    (tmp_vault.pkm_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(G)), encoding="utf-8"
    )
    return tmp_vault


def _write_graph_payload(path, graph_tier: str, node_id: str) -> None:
    graph = nx.DiGraph()
    graph.add_node(node_id, title=f"{graph_tier} node", type="note")
    payload = nx.node_link_data(graph)
    payload["graph_tier"] = graph_tier
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.anyio
async def test_full_graph_prefers_enriched_graph(
    app, vault_with_graph: VaultConfig
) -> None:
    """The full graph endpoint returns graph_enriched.json when both graphs exist."""
    _write_graph_payload(
        vault_with_graph.pkm_dir / "graph_enriched.json", "enriched", "enriched-node"
    )

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/graph",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        node_ids = {n.get("id") for n in data.get("nodes", [])}
        assert data["graph_tier"] == "enriched"
        assert "enriched-node" in node_ids
        assert "a" not in node_ids


@pytest.mark.anyio
async def test_full_graph_falls_back_to_plain_graph(
    app, vault_with_graph: VaultConfig
) -> None:
    """The full graph endpoint serves graph.json when no enriched graph exists."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/graph",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        node_ids = {n.get("id") for n in data.get("nodes", [])}
        assert {"a", "b", "c", "d"}.issubset(node_ids)


@pytest.mark.anyio
async def test_full_graph_missing_graph_returns_404(
    app, tmp_vault: VaultConfig
) -> None:
    """The full graph endpoint tells clients to index before graph data exists."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/graph",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 404
        assert "Graph not found" in resp.reason


@pytest.mark.anyio
async def test_full_graph_auth_required(app, vault_with_graph: VaultConfig) -> None:
    """The full graph endpoint is protected by bearer-token auth."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v1/vault/test-vault/graph")
        assert resp.status == 401


@pytest.mark.anyio
async def test_ego_radius_2_includes_two_hop_neighbors(
    app, vault_with_graph: VaultConfig
) -> None:
    """Ego from A at radius=2 must include A, B, and C."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/graph/ego/a",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        node_ids = {n.get("id") for n in data.get("nodes", [])}
        # The current note itself must be included.
        assert "a" in node_ids
        # Two-hop neighbours.
        assert "b" in node_ids
        assert "c" in node_ids
        # Disconnected island must NOT be included.
        assert "d" not in node_ids


@pytest.mark.anyio
async def test_ego_missing_note_returns_404(app, vault_with_graph: VaultConfig) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/graph/ego/no-such-note",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 404


@pytest.mark.anyio
async def test_ego_no_graph_returns_404(app, tmp_vault: VaultConfig) -> None:
    """When graph.json does not exist the route must 404 (not 500)."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/graph/ego/a",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 404


@pytest.mark.anyio
async def test_ego_auth_required(app, vault_with_graph: VaultConfig) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v1/vault/test-vault/graph/ego/a")
        assert resp.status == 401
