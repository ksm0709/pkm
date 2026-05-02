"""Tags REST handlers."""

from __future__ import annotations

from aiohttp import web

from pkm.web.routes.notes import _resolve_vault


async def list_tags(request: web.Request) -> web.Response:
    """GET /api/v1/vault/{name}/tags — list all tags with note counts."""
    vault = _resolve_vault(request.match_info["name"])

    from pkm.commands.tag_commands import count_all_tags

    pairs = count_all_tags(vault)
    items = [{"tag": tag, "count": count} for tag, count in pairs]
    return web.json_response({"tags": items, "count": len(items)})


async def search_tags(request: web.Request) -> web.Response:
    """GET /api/v1/vault/{name}/tags/search?pattern=... — pattern-filtered tag search."""
    vault = _resolve_vault(request.match_info["name"])
    pattern = request.rel_url.query.get("pattern", "").strip()

    if not pattern:
        raise web.HTTPBadRequest(
            reason="Query parameter 'pattern' is required and must not be empty"
        )

    from pkm.commands.tag_commands import search_by_tag_pattern

    mode, matched = search_by_tag_pattern(vault, pattern)
    items = [
        {
            "note_id": getattr(n, "id", None) or n.path.stem,
            "title": n.title,
            "tags": n.tags,
            "path": n.path.name,
        }
        for n in matched
    ]
    return web.json_response(
        {
            "pattern": pattern,
            "mode": mode,
            "results": items,
            "count": len(items),
        }
    )
