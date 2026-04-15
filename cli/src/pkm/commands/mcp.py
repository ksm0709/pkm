"""MCP server command for PKM CLI."""

from __future__ import annotations

import click


@click.command("mcp")
@click.option("--vault", "-v", "vault_name", default=None, help="Vault name")
@click.pass_context
def mcp_cmd(ctx: click.Context, vault_name: str | None) -> None:
    """Start MCP server for zeroclaw agents (stdio transport).

    Runs a foreground JSON-RPC 2.0 server on stdin/stdout. zeroclaw spawns
    this process automatically via config.toml registration.

    Tools exposed: note_add, daily_add, search, index.
    """
    try:
        from pkm.mcp_server import run_server
    except ImportError:
        raise click.ClickException(
            "MCP support requires the 'mcp' extra. Install with:\n"
            "  pip install pkm[mcp]"
        )

    from pkm.config import get_vault

    if vault_name:
        vault = get_vault(vault_name)
    elif ctx.obj and ctx.obj.get("vault"):
        vault = ctx.obj["vault"]
    else:
        vault = get_vault(None)

    run_server(vault)
