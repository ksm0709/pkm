"""Note-level REST handlers."""

from __future__ import annotations

import datetime
import json
from typing import Any

import networkx as nx
from aiohttp import web

from pkm.config import VaultConfig, discover_vaults
from pkm.frontmatter import parse, render
from pkm.note_lifecycle import validate_note_id
from pkm.note_summary import note_description as _shared_note_description


def _json_safe(obj: Any) -> Any:
    """Recursively convert YAML-parsed objects to JSON-serializable primitives."""
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(item) for item in obj]
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return obj


def _mtime_iso(path) -> str:
    return (
        datetime.datetime.fromtimestamp(path.stat().st_mtime, tz=datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _resolve_vault(name: str) -> VaultConfig:
    """Return the VaultConfig for *name*, or raise HTTP 404."""
    vaults = discover_vaults()
    if name not in vaults:
        raise web.HTTPNotFound(reason=f"Vault '{name}' not found")
    return vaults[name]


def _tag_scan_neighbors(vault: VaultConfig, note_id: str) -> list[dict]:
    """Return notes carrying a tag by scanning current markdown files."""
    if not note_id.startswith("tag:"):
        return []
    tag = note_id.removeprefix("tag:")
    if not tag:
        return []

    items: list[dict] = []
    seen: set[str] = set()
    for base_dir in (vault.notes_dir, vault.daily_dir):
        if not base_dir.is_dir():
            continue
        for md_file in sorted(base_dir.glob("*.md")):
            try:
                note = parse(md_file)
            except Exception:
                continue
            if tag not in note.tags:
                continue
            scanned_id = str(note.id)
            if scanned_id in seen:
                continue
            seen.add(scanned_id)
            items.append(
                {
                    "note_id": scanned_id,
                    "title": str(note.title),
                    "type": "note",
                    "description": _note_description(note.meta, note.body),
                }
            )
    return items


def _note_description(meta: dict, body: str = "") -> str:
    return _shared_note_description(meta, body)


def _node_description(attrs: dict) -> str:
    meta = attrs.get("meta") if isinstance(attrs.get("meta"), dict) else {}
    return _note_description(meta)


def _title_from_note_id(note_id: str) -> str:
    return note_id.replace("-", " ").replace("_", " ").strip() or note_id


def _validate_app_creatable_note_id(note_id: str) -> None:
    try:
        validate_note_id(note_id)
    except ValueError:
        raise web.HTTPBadRequest(reason="Invalid note id")


def _ensure_blank_note(vault: VaultConfig, note_id: str):
    """Create an exact-id blank note for unresolved app wikilinks."""
    _validate_app_creatable_note_id(note_id)
    for base_dir in (vault.notes_dir, vault.daily_dir, vault.tags_dir):
        path = base_dir / f"{note_id}.md"
        if path.exists():
            return path, False

    vault.notes_dir.mkdir(parents=True, exist_ok=True)
    path = vault.notes_dir / f"{note_id}.md"
    resolved = path.resolve()
    if vault.notes_dir.resolve() not in resolved.parents:
        raise web.HTTPBadRequest(reason="Invalid note id")

    title = _title_from_note_id(note_id)
    meta = {"id": note_id, "title": title, "aliases": [], "tags": []}
    path.write_text(render(meta, ""), encoding="utf-8")
    return path, True


def _neighbors_data(vault: VaultConfig, note_id: str) -> dict:
    """Return neighbor graph data with semantic edges enabled.

    Mirrors pkm.tools.links._get_note_neighbors_data with include_semantic=True,
    inlined here to avoid the tiny_agent dependency in the tools package.
    """
    graph_path = vault.pkm_dir / "graph.json"
    if not graph_path.exists():
        if note_id.startswith("tag:"):
            return {
                "note_id": note_id,
                "outbound": [],
                "inbound": _tag_scan_neighbors(vault, note_id),
                "semantic": [],
            }
        raise FileNotFoundError("graph not found — run pkm index first")

    G = nx.node_link_graph(json.loads(graph_path.read_text()))
    if note_id not in G:
        return {
            "note_id": note_id,
            "outbound": [],
            "inbound": _tag_scan_neighbors(vault, note_id),
            "semantic": [],
        }

    def _node(n: str) -> dict:
        attrs = G.nodes[n]
        return {
            "note_id": n,
            "title": attrs.get("title", n),
            "type": attrs.get("type", "note"),
            "description": _node_description(attrs),
        }

    outbound = [_node(n) for n in G.successors(note_id)]
    inbound = [_node(n) for n in G.predecessors(note_id)]
    if note_id.startswith("tag:"):
        seen_inbound = {item["note_id"] for item in inbound}
        for item in _tag_scan_neighbors(vault, note_id):
            if item["note_id"] not in seen_inbound:
                inbound.append(item)
                seen_inbound.add(item["note_id"])

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
            attrs = EG.nodes[neighbor]
            semantic.append(
                {
                    "note_id": neighbor,
                    "title": attrs.get("title", neighbor),
                    "type": attrs.get("type", "note"),
                    "confidence": edata.get("confidence", 0.0),
                    "description": _node_description(attrs),
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
        for md_file in vault.notes_dir.glob("*.md"):
            try:
                note = parse(md_file)
                fm = note.meta or {}
                modified_at = _mtime_iso(md_file)
                results.append(
                    {
                        "note_id": note.id,
                        "title": note.title,
                        "path": md_file.name,
                        "description": _note_description(fm, note.body),
                        "tags": note.tags,
                        "created_at": _json_safe(
                            fm.get("created_at") or fm.get("source") or None
                        ),
                        "updated_at": _json_safe(fm.get("updated_at") or None),
                        "modified_at": modified_at,
                    }
                )
            except Exception:
                pass
    results.sort(
        key=lambda item: (
            item.get("modified_at") or "",
            item.get("updated_at") or "",
            item.get("created_at") or "",
            item.get("note_id") or "",
        ),
        reverse=True,
    )
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
                    "note_id": str(note.id),
                    "title": str(note.title),
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


def _note_response(path) -> dict:
    """Build the 8-key note response dict from a file path."""
    note = parse(path)
    fm = note.meta or {}
    importance_raw = fm.get("importance")
    importance = int(importance_raw) if importance_raw is not None else None
    return {
        "note_id": str(note.id),
        "title": str(note.title),
        "body": note.body,
        "frontmatter": _json_safe(fm),
        "created": _json_safe(fm.get("created_at") or fm.get("source") or None),
        "updated": _json_safe(fm.get("updated_at") or None),
        "tags": note.tags,
        "importance": importance,
    }


async def create_note_handler(request: web.Request) -> web.Response:
    """POST /api/v1/vault/{name}/notes — create a new note."""
    vault = _resolve_vault(request.match_info["name"])

    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON body")

    title = data.get("title")
    body = data.get("body", "")
    tags = data.get("tags") or []

    if not title:
        raise web.HTTPBadRequest(reason="Field 'title' is required")

    from pkm.commands.notes import create_note

    try:
        # Pass content=None so generate_frontmatter (not memory frontmatter) is used.
        # Store title explicitly in frontmatter so note.title returns the human title.
        note_path = create_note(
            vault=vault,
            title=title,
            content=None,
            tags=tags,
            no_dedup=True,
            meta={"title": title},
        )
    except FileExistsError as exc:
        raise web.HTTPConflict(reason=str(exc))
    except ValueError as exc:
        raise web.HTTPBadRequest(reason=str(exc))

    # Write body after creation if provided (create_note used content=None)
    if body:
        note = parse(note_path)
        note_path.write_text(render(dict(note.meta), body), encoding="utf-8")

    return web.json_response(_note_response(note_path), status=201)


async def ensure_note_handler(request: web.Request) -> web.Response:
    """POST /api/v1/vault/{name}/notes/{id}/ensure — create unresolved note."""
    vault = _resolve_vault(request.match_info["name"])
    note_id = request.match_info["id"]
    path, created = _ensure_blank_note(vault, note_id)
    return web.json_response(_note_response(path), status=201 if created else 200)


async def update_note(request: web.Request) -> web.Response:
    """PUT /api/v1/vault/{name}/notes/{id} — update note body (and optionally title/tags)."""
    vault = _resolve_vault(request.match_info["name"])
    note_id = request.match_info["id"]

    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON body")

    for base_dir in (vault.notes_dir, vault.daily_dir):
        path = base_dir / f"{note_id}.md"
        if path.exists():
            note = parse(path)
            new_body = data.get("body", note.body)
            meta = dict(note.meta or {})
            if "title" in data:
                meta["title"] = data["title"]
            if "tags" in data:
                meta["tags"] = data["tags"]
            path.write_text(render(meta, new_body), encoding="utf-8")
            return web.json_response(_note_response(path))

    raise web.HTTPNotFound(reason=f"Note '{note_id}' not found in vault '{vault.name}'")


async def batch_titles(request: web.Request) -> web.Response:
    """POST /api/v1/vault/{name}/notes/batch-titles — resolve note IDs to titles.

    Body: {"ids": [string]}
    Response: {id: title} mapping; unresolved IDs map to "".
    400 if ids is not a list or len(ids) > 200.
    """
    vault = _resolve_vault(request.match_info["name"])

    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON body")

    ids = data.get("ids")
    if not isinstance(ids, list):
        raise web.HTTPBadRequest(reason="'ids' must be a list")
    if len(ids) > 200:
        raise web.HTTPBadRequest(reason="'ids' must contain at most 200 items")

    result: dict[str, str] = {}
    for note_id in ids:
        note_id_str = str(note_id)
        resolved = ""
        for base_dir in (vault.notes_dir, vault.daily_dir):
            path = base_dir / f"{note_id_str}.md"
            if path.exists():
                try:
                    note = parse(path)
                    resolved = str(note.title) if note.title else note_id_str
                except Exception:
                    pass
                break
        result[note_id_str] = resolved

    return web.json_response(result)
