"""Vault-level REST handlers."""

from __future__ import annotations

from aiohttp import web

from pkm.config import discover_vaults, get_vault_context


async def get_vaults(request: web.Request) -> web.Response:
    """GET /api/v1/vaults — list all discovered vaults."""
    vaults = discover_vaults()
    try:
        default_vault, _ = get_vault_context()
        default_name = default_vault.name
    except Exception:
        default_name = next(iter(vaults), None)
    return web.json_response(
        [
            {
                "name": name,
                "path": str(v.path),
                "is_default": name == default_name,
            }
            for name, v in vaults.items()
        ]
    )
