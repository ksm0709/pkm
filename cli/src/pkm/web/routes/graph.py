"""Graph REST handlers."""

from __future__ import annotations

import json

import networkx as nx
from aiohttp import web

from pkm.web.routes.notes import _resolve_vault


async def get_graph(request: web.Request) -> web.Response:
    """GET /api/v1/vault/{name}/graph — return the full graph as node-link JSON.

    Prefers graph_enriched.json; falls back to graph.json. 404 if neither exists.
    """
    vault = _resolve_vault(request.match_info["name"])

    enriched_path = vault.pkm_dir / "graph_enriched.json"
    plain_path = vault.pkm_dir / "graph.json"

    if enriched_path.exists():
        graph_path = enriched_path
    elif plain_path.exists():
        graph_path = plain_path
    else:
        raise web.HTTPNotFound(reason="Graph not found — run 'pkm index' first")

    data = json.loads(graph_path.read_text(encoding="utf-8"))
    return web.json_response(data)


async def get_ego_graph(request: web.Request) -> web.Response:
    """GET /api/v1/vault/{name}/graph/ego/{note_id} — 2-hop ego subgraph."""
    vault = _resolve_vault(request.match_info["name"])
    note_id = request.match_info["note_id"]

    plain_path = vault.pkm_dir / "graph.json"
    if not plain_path.exists():
        raise web.HTTPNotFound(reason="Graph not found — run 'pkm index' first")

    G = nx.node_link_graph(json.loads(plain_path.read_text(encoding="utf-8")))

    if note_id not in G:
        raise web.HTTPNotFound(reason=f"Note '{note_id}' not found in graph")

    ego = nx.ego_graph(G, note_id, radius=2)
    return web.json_response(nx.node_link_data(ego))
