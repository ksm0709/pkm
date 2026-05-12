"""Search REST handler."""

from __future__ import annotations

import asyncio
from pathlib import Path

from aiohttp import web
from click import ClickException

from pkm.frontmatter import parse as parse_note
from pkm.web.app_keys import SEARCH_RUNNER_KEY
from pkm.web.routes.notes import _resolve_vault


def _extract_snippet(body: str, max_len: int = 200) -> str:
    """Return the first non-empty line from the note body."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:max_len]
    return ""


async def search_notes(request: web.Request) -> web.Response:
    """GET /api/v1/vault/{name}/search?q=... — semantic full-text search."""
    vault = _resolve_vault(request.match_info["name"])
    query = request.rel_url.query.get("q", "").strip()

    if not query:
        raise web.HTTPBadRequest(
            reason="Query parameter 'q' is required and must not be empty"
        )

    try:
        top_n = int(request.rel_url.query.get("n", "10"))
    except ValueError:
        raise web.HTTPBadRequest(reason="'n' must be an integer")
    top_n = min(max(1, top_n), 100)

    try:
        search_runner = request.app.get(SEARCH_RUNNER_KEY)
        if search_runner is not None:
            results, stale_warning = await search_runner(query, vault, top=top_n)
        else:
            from pkm.commands.search import run_search_pipeline

            results, stale_warning = run_search_pipeline(query, vault, top=top_n)
    except (FileNotFoundError, ClickException):
        raise web.HTTPNotFound(reason="Search index not found — run 'pkm index' first")

    items = []
    for r in results:
        snippet = ""
        try:
            note = parse_note(Path(r.path))
            snippet = _extract_snippet(note.body)
        except Exception:
            pass
        items.append(
            {
                "note_id": str(r.note_id),
                "title": str(r.title),
                "snippet": snippet,
                "score": round(r.score, 6),
            }
        )

    payload = {
        "query": query,
        "count": len(items),
        "results": items,
    }
    if stale_warning:
        payload["warning"] = stale_warning
    return web.json_response(payload)


async def index_vault(request: web.Request) -> web.Response:
    """POST /api/v1/vault/{name}/index — rebuild search index and graphs."""
    vault = _resolve_vault(request.match_info["name"])

    try:
        from pkm.search_engine import build_index

        vector_index = await asyncio.to_thread(build_index, vault)
    except ClickException as exc:
        raise web.HTTPServiceUnavailable(reason=str(exc))

    return web.json_response(
        {
            "status": "ok",
            "count": len(vector_index.entries),
            "index_path": str(vault.pkm_dir / "index.json"),
            "graph_path": str(vault.pkm_dir / "graph.json"),
        }
    )
