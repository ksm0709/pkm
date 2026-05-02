"""Note-level REST handlers."""

from __future__ import annotations

import datetime
from typing import Any

from aiohttp import web

from pkm.config import VaultConfig, discover_vaults
from pkm.frontmatter import parse
from pkm.tools.links import _get_note_neighbors_data


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
        data = _get_note_neighbors_data(vault, note_id, include_semantic=True)
    except FileNotFoundError as exc:
        raise web.HTTPNotFound(reason=str(exc))
    return web.json_response(data)
