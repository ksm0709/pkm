"""REST route registration for the PKM web server."""

from __future__ import annotations

from aiohttp import web

from pkm.web.routes.annotations import (
    get_data_annotations,
    get_note_annotations,
    patch_note_annotation_anchors,
    put_data_annotations,
    put_note_annotations,
)
from pkm.web.routes.configs import get_configs, patch_config_setting
from pkm.web.routes.daily import (
    get_daily_date,
    get_daily_today,
    list_daily,
    post_daily_today,
)
from pkm.web.routes.data import (
    get_data_file,
    get_human_data_file,
    get_pdf_annotations,
    post_data_file,
    put_pdf_annotations,
)
from pkm.web.routes.feedback import get_feedback, post_feedback
from pkm.web.routes.graph import get_ego_graph, get_graph
from pkm.web.routes.notes import (
    batch_titles,
    create_note_handler,
    ensure_note_handler,
    get_note,
    get_note_neighbors,
    list_notes,
    update_note,
)
from pkm.web.routes.search import index_vault, search_notes
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
    app.router.add_post("/api/v1/vault/{name}/notes/{id}/ensure", ensure_note_handler)
    app.router.add_put("/api/v1/vault/{name}/notes/{id}", update_note)

    # Notes — batch operations (literal path must come before /{id} catch-all)
    app.router.add_post("/api/v1/vault/{name}/notes/batch-titles", batch_titles)

    # Daily — /today must be registered before /{date} to win literal match
    app.router.add_get("/api/v1/vault/{name}/daily/today", get_daily_today)
    app.router.add_post("/api/v1/vault/{name}/daily/today", post_daily_today)
    app.router.add_get("/api/v1/vault/{name}/daily/{date}", get_daily_date)
    app.router.add_get("/api/v1/vault/{name}/daily", list_daily)

    # Feedback — each submission is a tagged daily subnote and daily-log entry.
    app.router.add_get("/api/v1/vault/{name}/feedback", get_feedback)
    app.router.add_post("/api/v1/vault/{name}/feedback", post_feedback)

    # Unified annotations — source-scoped v2 sidecars.
    app.router.add_get(
        "/api/v1/vault/{name}/annotations/data/{path:.+}", get_data_annotations
    )
    app.router.add_put(
        "/api/v1/vault/{name}/annotations/data/{path:.+}", put_data_annotations
    )
    app.router.add_get(
        "/api/v1/vault/{name}/annotations/note/{id}", get_note_annotations
    )
    app.router.add_put(
        "/api/v1/vault/{name}/annotations/note/{id}", put_note_annotations
    )
    app.router.add_patch(
        "/api/v1/vault/{name}/annotations/note/{id}",
        patch_note_annotation_anchors,
    )

    # Data files — flat and nested files under vault data/
    app.router.add_post("/api/v1/vault/{name}/data", post_data_file)
    app.router.add_get(
        "/api/v1/vault/{name}/data-annotations/{path:.+}", get_pdf_annotations
    )
    app.router.add_put(
        "/api/v1/vault/{name}/data-annotations/{path:.+}", put_pdf_annotations
    )
    app.router.add_get("/api/v1/vault/{name}/data/{filename}", get_data_file)
    app.router.add_get("/api/v1/vault/{name}/data/{path:.+}", get_data_file)
    app.router.add_get("/{name}/data/{path:.+}", get_human_data_file)

    # Search
    app.router.add_post("/api/v1/vault/{name}/index", index_vault)
    app.router.add_get("/api/v1/vault/{name}/search", search_notes)

    # Tags — /search must be registered before generic pattern routes
    app.router.add_get("/api/v1/vault/{name}/tags/search", search_tags)
    app.router.add_get("/api/v1/vault/{name}/tags", list_tags)

    # Graph — /ego/{note_id} must be registered before generic routes
    app.router.add_get("/api/v1/vault/{name}/graph/ego/{note_id}", get_ego_graph)
    app.router.add_get("/api/v1/vault/{name}/graph", get_graph)


    # Configs
    app.router.add_get("/api/v1/vault/{name}/configs", get_configs)
    app.router.add_patch(
        "/api/v1/vault/{name}/configs/settings/{key}",
        patch_config_setting,
    )
