"""REST route registration for the PKM web server."""

from __future__ import annotations

from aiohttp import web

from pkm.web.routes.ask import post_ask
from pkm.web.routes.daily import (
    get_daily_date,
    get_daily_today,
    list_daily,
    post_daily_today,
)
from pkm.web.routes.graph import get_ego_graph, get_graph
from pkm.web.routes.notes import (
    create_note_handler,
    get_note,
    get_note_neighbors,
    list_notes,
    update_note,
)
from pkm.web.routes.search import search_notes
from pkm.web.routes.tags import list_tags, search_tags
from pkm.web.routes.vault import get_vaults


def register_routes(app: web.Application) -> None:
    """Register all REST routes onto *app*."""
    # Vault
    app.router.add_get("/api/v1/vaults", get_vaults)

    # Notes — read
    app.router.add_get("/api/v1/vault/{name}/notes", list_notes)
    app.router.add_get("/api/v1/vault/{name}/notes/{id}", get_note)
    app.router.add_get("/api/v1/vault/{name}/notes/{id}/neighbors", get_note_neighbors)

    # Notes — write
    app.router.add_post("/api/v1/vault/{name}/notes", create_note_handler)
    app.router.add_put("/api/v1/vault/{name}/notes/{id}", update_note)

    # Daily — /today must be registered before /{date} to win literal match
    app.router.add_get("/api/v1/vault/{name}/daily/today", get_daily_today)
    app.router.add_post("/api/v1/vault/{name}/daily/today", post_daily_today)
    app.router.add_get("/api/v1/vault/{name}/daily/{date}", get_daily_date)
    app.router.add_get("/api/v1/vault/{name}/daily", list_daily)

    # Search
    app.router.add_get("/api/v1/vault/{name}/search", search_notes)

    # Tags — /search must be registered before generic pattern routes
    app.router.add_get("/api/v1/vault/{name}/tags/search", search_tags)
    app.router.add_get("/api/v1/vault/{name}/tags", list_tags)

    # Graph — /ego/{note_id} must be registered before generic routes
    app.router.add_get("/api/v1/vault/{name}/graph/ego/{note_id}", get_ego_graph)
    app.router.add_get("/api/v1/vault/{name}/graph", get_graph)

    # Ask — SSE
    app.router.add_post("/api/v1/vault/{name}/ask", post_ask)
