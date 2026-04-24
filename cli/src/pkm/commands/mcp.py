"""MCP server command for PKM CLI."""

from __future__ import annotations

import click


@click.group("mcp", invoke_without_command=True)
@click.option("--vault", "-v", "vault_name", default=None, help="Vault name")
@click.pass_context
def mcp_cmd(ctx: click.Context, vault_name: str | None) -> None:
    """Start MCP server (stdio transport).

    Runs a foreground JSON-RPC 2.0 server on stdin/stdout. An MCP client
    spawns this process automatically via its server configuration.

    Tools exposed: note_add, daily_add, search, index.
    """
    if ctx.invoked_subcommand is None:
        from pkm.mcp_server import run_server
        from pkm.config import get_vault

        if vault_name:
            vault = get_vault(vault_name)
        else:
            vault = ctx.obj.get("vault") if ctx.obj else get_vault(None)

        run_server(vault)


@mcp_cmd.command("install")
@click.argument("targets", nargs=-1)
@click.option("--vault", "-v", "vault_name", default=None, help="Vault name to bind MCP server to")
@click.pass_context
def install_cmd(ctx: click.Context, targets: tuple[str, ...], vault_name: str | None) -> None:
    import json
    import subprocess
    from pathlib import Path
    from pkm.config import get_vault

    if not targets or "all" in targets:
        targets = ("claude", "codex", "opencode")

    vault_obj = ctx.obj.get("vault") if ctx.obj else None
    if vault_name:
        vault_obj = get_vault(vault_name)
    elif vault_obj is None:
        vault_obj = get_vault(None)

    vault_arg = vault_obj.name if vault_obj else None
    mcp_args = ["mcp", "--vault", vault_arg] if vault_arg else ["mcp"]

    for target in targets:
        if target == "claude":
            try:
                result = subprocess.run(
                    ["claude", "mcp", "add", "pkm", "--", "pkm"] + mcp_args,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    click.echo(f"Installed PKM MCP to Claude Code (vault: {vault_arg or 'auto'})")
                else:
                    click.echo(
                        f"Failed to install to Claude Code: {result.stderr}", err=True
                    )
            except FileNotFoundError:
                click.echo("Claude Code CLI not found in PATH", err=True)

        elif target == "codex":
            config_path = Path.home() / ".codex" / "config.toml"
            if not config_path.exists():
                click.echo("~/.codex/config.toml not found", err=True)
                continue

            try:
                content = config_path.read_text(encoding="utf-8")
                if "[mcp_servers.pkm]" in content:
                    click.echo("PKM MCP already configured in Codex")
                    continue

                args_toml = json.dumps(mcp_args)
                new_server = f'\n[mcp_servers.pkm]\ncommand = "pkm"\nargs = {args_toml}\n'
                if not content.endswith("\n"):
                    content += "\n"
                content += new_server
                config_path.write_text(content, encoding="utf-8")
                click.echo(f"Installed PKM MCP to Codex (vault: {vault_arg or 'auto'}, {config_path})")
            except Exception as e:
                click.echo(f"Error writing {config_path}: {e}", err=True)

        elif target == "opencode":
            config_path = Path.home() / ".config" / "opencode" / "opencode.json"
            if not config_path.exists():
                click.echo("~/.config/opencode/opencode.json not found", err=True)
                continue

            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                mcp_servers = data.setdefault("mcp", {})
                if "pkm" in mcp_servers:
                    click.echo("PKM MCP already configured in OpenCode")
                    continue

                mcp_servers["pkm"] = {
                    "type": "local",
                    "command": ["pkm"] + mcp_args,
                    "enabled": True,
                }

                config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                click.echo(f"Installed PKM MCP to OpenCode (vault: {vault_arg or 'auto'}, {config_path})")
            except Exception as e:
                click.echo(f"Error writing {config_path}: {e}", err=True)
        else:
            click.echo(
                f"Unknown target: {target}. Valid targets: claude, codex, opencode, all",
                err=True,
            )
