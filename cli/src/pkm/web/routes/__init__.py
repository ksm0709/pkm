"""REST route registration for the PKM web server."""

from __future__ import annotations

from aiohttp import web

from pkm.web.routes.daily import (
    get_daily_date,
    get_daily_today,
    list_daily,
    post_daily_today,
)
from pkm.web.routes.notes import (
    create_note_handler,
    get_note,
    get_note_neighbors,
    list_notes,
    update_note,
)
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
