"""MCP server command for PKM CLI."""

from __future__ import annotations

import click


@click.command("mcp")
@click.option("--vault", "-v", "vault_name", default=None, help="Vault name")
@click.pass_context
def mcp_cmd(ctx: click.Context, vault_name: str | None) -> None:
    """Start MCP server (stdio transport).

    Runs a foreground JSON-RPC 2.0 server on stdin/stdout. An MCP client
    spawns this process automatically via its server configuration.

    Tools exposed: note_add, daily_add, search, index.
    """
    from pkm.mcp_server import run_server

    from pkm.config import get_vault

    if vault_name:
        vault = get_vault(vault_name)
    else:
        vault = ctx.obj.get("vault") if ctx.obj else get_vault(None)

    run_server(vault)
