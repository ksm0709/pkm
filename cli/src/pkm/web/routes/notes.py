"""Note-level REST handlers."""

from __future__ import annotations

import datetime
import json
from typing import Any

import networkx as nx
from aiohttp import web

from pkm.config import VaultConfig, discover_vaults
from pkm.frontmatter import parse


def _json_safe(obj: Any) -> Any:
    """Recursively convert YAML-parsed objects to JSON-serializable primitives."""
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(item) for item in obj]
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return obj


def _resolve_vault(name: str) -> VaultConfig:
    """Return the VaultConfig for *name*, or raise HTTP 404."""
    vaults = discover_vaults()
    if name not in vaults:
        raise web.HTTPNotFound(reason=f"Vault '{name}' not found")
    return vaults[name]


def _neighbors_data(vault: VaultConfig, note_id: str) -> dict:
    """Return neighbor graph data with semantic edges enabled.

    Mirrors pkm.tools.links._get_note_neighbors_data with include_semantic=True,
    inlined here to avoid the tiny_agent dependency in the tools package.
    """
    graph_path = vault.pkm_dir / "graph.json"
    if not graph_path.exists():
        raise FileNotFoundError("graph not found — run pkm index first")

    G = nx.node_link_graph(json.loads(graph_path.read_text()))
    if note_id not in G:
        return {"note_id": note_id, "outbound": [], "inbound": [], "semantic": []}

    def _node(n: str) -> dict:
        return {
            "note_id": n,
            "title": G.nodes[n].get("title", n),
            "type": G.nodes[n].get("type", "note"),
        }

    outbound = [_node(n) for n in G.successors(note_id)]
    inbound = [_node(n) for n in G.predecessors(note_id)]

    semantic: list[dict] = []
    enriched_path = vault.pkm_dir / "graph_enriched.json"
    if enriched_path.exists():
        EG = nx.node_link_graph(json.loads(enriched_path.read_text()))
        seen: set[str] = set()
        for src, tgt, edata in EG.edges(data=True):
            if edata.get("type") != "semantic_similar":
                continue
            neighbor = tgt if src == note_id else (src if tgt == note_id else None)
            if neighbor is None or neighbor in seen:
                continue
            seen.add(neighbor)
            semantic.append(
                {
                    "note_id": neighbor,
                    "title": EG.nodes[neighbor].get("title", neighbor),
                    "type": EG.nodes[neighbor].get("type", "note"),
                    "confidence": edata.get("confidence", 0.0),
                }
            )

    return {
        "note_id": note_id,
        "outbound": outbound,
        "inbound": inbound,
        "semantic": semantic,
    }


async def list_notes(request: web.Request) -> web.Response:
    """GET /api/v1/vault/{name}/notes — list notes in vault."""
    vault = _resolve_vault(request.match_info["name"])

    results = []
    if vault.notes_dir.is_dir():
        for md_file in sorted(vault.notes_dir.glob("*.md")):
            try:
                note = parse(md_file)
                fm = note.meta or {}
                results.append(
                    {
                        "note_id": note.id,
                        "title": note.title,
                        "path": md_file.name,
                        "tags": note.tags,
                        "created_at": _json_safe(
                            fm.get("created_at") or fm.get("source") or None
                        ),
                    }
                )
            except Exception:
                pass
    return web.json_response(results)


async def get_note(request: web.Request) -> web.Response:
    """GET /api/v1/vault/{name}/notes/{id} — fetch one note (8-key schema)."""
    vault = _resolve_vault(request.match_info["name"])
    note_id = request.match_info["id"]

    for base_dir in (vault.notes_dir, vault.daily_dir):
        path = base_dir / f"{note_id}.md"
        if path.exists():
            note = parse(path)
            fm = note.meta or {}
            importance_raw = fm.get("importance")
            importance = int(importance_raw) if importance_raw is not None else None
            return web.json_response(
                {
                    "note_id": note.id,
                    "title": note.title,
                    "body": note.body,
                    "frontmatter": _json_safe(fm),
                    "created": _json_safe(
                        fm.get("created_at") or fm.get("source") or None
                    ),
                    "updated": _json_safe(fm.get("updated_at") or None),
                    "tags": note.tags,
                    "importance": importance,
                }
            )

    raise web.HTTPNotFound(reason=f"Note '{note_id}' not found in vault '{vault.name}'")


async def get_note_neighbors(request: web.Request) -> web.Response:
    """GET /api/v1/vault/{name}/notes/{id}/neighbors — neighbor graph data."""
    vault = _resolve_vault(request.match_info["name"])
    note_id = request.match_info["id"]

    try:
        data = _neighbors_data(vault, note_id)
    except FileNotFoundError as exc:
        raise web.HTTPNotFound(reason=str(exc))
    return web.json_response(data)
