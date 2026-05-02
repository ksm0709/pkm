"""REST route registration for the PKM web server."""

from __future__ import annotations

from aiohttp import web

from pkm.web.routes.notes import get_note, get_note_neighbors, list_notes
from pkm.web.routes.vault import get_vaults


def register_routes(app: web.Application) -> None:
    """Register all read-only REST routes onto *app*."""
    app.router.add_get("/api/v1/vaults", get_vaults)
    app.router.add_get("/api/v1/vault/{name}/notes", list_notes)
    app.router.add_get("/api/v1/vault/{name}/notes/{id}", get_note)
    app.router.add_get("/api/v1/vault/{name}/notes/{id}/neighbors", get_note_neighbors)
