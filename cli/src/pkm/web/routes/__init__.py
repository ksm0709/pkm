"""REST route registration for the PKM web server."""

from __future__ import annotations

from aiohttp import web

from pkm.web.routes.ask import get_ask_options, get_ask_run, post_ask
from pkm.web.routes.configs import (
    delete_ask_credential,
    get_configs,
    patch_config_setting,
    put_ask_credential,
)
from pkm.web.routes.daily import (
    get_daily_date,
    get_daily_today,
    list_daily,
    post_daily_today,
)
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
from pkm.web.routes.search import search_notes
from pkm.web.routes.tags import list_tags, search_tags
from pkm.web.routes.vault import get_vaults
from pkm.web.routes.workflows import (
    get_workflow,
    get_workflow_history,
    get_workflow_run_status,
    list_workflow_history,
    list_workflows,
    run_workflow,
    update_workflow,
)


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

    # Search
    app.router.add_get("/api/v1/vault/{name}/search", search_notes)

    # Tags — /search must be registered before generic pattern routes
    app.router.add_get("/api/v1/vault/{name}/tags/search", search_tags)
    app.router.add_get("/api/v1/vault/{name}/tags", list_tags)

    # Graph — /ego/{note_id} must be registered before generic routes
    app.router.add_get("/api/v1/vault/{name}/graph/ego/{note_id}", get_ego_graph)
    app.router.add_get("/api/v1/vault/{name}/graph", get_graph)

    # Ask — SSE
    app.router.add_get("/api/v1/vault/{name}/ask/options", get_ask_options)
    app.router.add_get("/api/v1/vault/{name}/ask/runs/{run_id}", get_ask_run)
    app.router.add_post("/api/v1/vault/{name}/ask", post_ask)

    # Configs
    app.router.add_get("/api/v1/vault/{name}/configs", get_configs)
    app.router.add_patch(
        "/api/v1/vault/{name}/configs/settings/{key}",
        patch_config_setting,
    )
    app.router.add_put(
        "/api/v1/vault/{name}/configs/ask/credentials/{provider}",
        put_ask_credential,
    )
    app.router.add_delete(
        "/api/v1/vault/{name}/configs/ask/credentials/{provider}",
        delete_ask_credential,
    )

    # Workflows
    app.router.add_get("/api/v1/vault/{name}/workflow-history", list_workflow_history)
    app.router.add_get("/api/v1/vault/{name}/workflows", list_workflows)
    app.router.add_get(
        "/api/v1/vault/{name}/workflows/{id}/history",
        get_workflow_history,
    )
    app.router.add_get(
        "/api/v1/vault/{name}/workflows/{id}/run-status",
        get_workflow_run_status,
    )
    app.router.add_post("/api/v1/vault/{name}/workflows/{id}/run", run_workflow)
    app.router.add_get("/api/v1/vault/{name}/workflows/{id}", get_workflow)
    app.router.add_patch("/api/v1/vault/{name}/workflows/{id}", update_workflow)
