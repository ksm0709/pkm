"""Vault-level REST handlers."""

from __future__ import annotations

from aiohttp import web

from pkm.config import discover_vaults


async def get_vaults(request: web.Request) -> web.Response:
    """GET /api/v1/vaults — list all discovered vaults."""
    vaults = discover_vaults()
    return web.json_response(
        [{"name": name, "path": str(v.path)} for name, v in vaults.items()]
    )
