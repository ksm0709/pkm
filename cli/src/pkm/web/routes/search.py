"""Search REST handler."""

from __future__ import annotations

from aiohttp import web

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

    from pkm.search_engine import load_index, search as search_fn
    from pkm.frontmatter import parse as parse_note
    from pathlib import Path

    try:
        index = load_index(vault)
    except FileNotFoundError:
        raise web.HTTPNotFound(reason="Search index not found — run 'pkm index' first")

    results = search_fn(query, index, top_n=top_n)

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
                "note_id": r.note_id,
                "title": r.title,
                "snippet": snippet,
                "score": round(r.score, 6),
            }
        )

    return web.json_response(
        {
            "query": query,
            "count": len(items),
            "results": items,
        }
    )
