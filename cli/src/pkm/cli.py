"""PKM CLI entrypoint."""

from __future__ import annotations

import click
from rich.console import Console

from pkm import __version__
from pkm.commands.config import config
from pkm.commands.daily import daily
from pkm.commands.links import orphans
from pkm.commands.notes import new
from pkm.commands.maintenance import stale, stats, tags
from pkm.commands.search import index_cmd, search_cmd
from pkm.commands.setup import setup_cmd
from pkm.commands.vault import vault
from pkm.config import get_vault

VAULT_FREE_COMMANDS = {"vault", "config", "setup"}

_console = Console()


@click.group(invoke_without_command=True)
@click.option("--vault", "-v", default=None, help="Vault name (default: auto-detected)")
@click.version_option(version=__version__, prog_name="pkm")
@click.pass_context
def main(ctx: click.Context, vault: str | None) -> None:
    """Personal Knowledge Management CLI for Obsidian vaults."""
    ctx.ensure_object(dict)
    if ctx.invoked_subcommand is None:
        _console.print(f"[bold]pkm[/bold] v{__version__} — Personal Knowledge Management CLI")
        _console.print()
        _console.print("Run [bold cyan]pkm --help[/bold cyan] for available commands.")
        _console.print("Run [bold cyan]pkm setup[/bold cyan] to configure vaults and install the skill.")
        return
    if ctx.invoked_subcommand not in VAULT_FREE_COMMANDS:
        ctx.obj["vault"] = get_vault(vault)


main.add_command(daily)
main.add_command(new)
main.add_command(orphans)
main.add_command(index_cmd)
main.add_command(search_cmd)
main.add_command(tags)
main.add_command(stats)
main.add_command(stale)
main.add_command(vault)
main.add_command(config)
main.add_command(setup_cmd)
