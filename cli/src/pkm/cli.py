"""PKM CLI entrypoint."""

from __future__ import annotations

import click
from rich.console import Console

from pkm import __version__
from pkm.version_check import available_update
from pkm.commands.config import config
from pkm.commands.daily import daily
from pkm.commands.links import orphans
from pkm.commands.notes import note
from pkm.commands.maintenance import stats
from pkm.commands.tag_commands import tags
from pkm.commands.search import index_cmd, search_cmd
from pkm.commands.setup import setup_cmd
from pkm.commands.agent import agent
from pkm.commands.consolidate import consolidate
from pkm.commands.update import update_cmd
from pkm.commands.vault import vault
from pkm.config import get_vault

VAULT_FREE_COMMANDS = {"vault", "config", "setup", "update"}

_console = Console()


@click.group(invoke_without_command=True)
@click.option("--vault", "-v", default=None, help="Vault name (default: auto-detected)")
@click.version_option(version=__version__, prog_name="pkm")
@click.pass_context
def main(ctx: click.Context, vault: str | None) -> None:
    """Personal Knowledge Management CLI for Obsidian vaults."""
    ctx.ensure_object(dict)
    newer = available_update(__version__)
    if newer:
        _console.print(
            f"[bold yellow]⚡ pkm {newer} available[/bold yellow] "
            f"[dim](current: v{__version__})[/dim]  "
            "Run [bold cyan]pkm update[/bold cyan] to upgrade."
        )
    if ctx.invoked_subcommand is None:
        _console.print(
            f"[bold]pkm[/bold] v{__version__} — Personal Knowledge Management CLI"
        )
        try:
            from pkm.config import get_vault_context

            vc, source = get_vault_context(vault)
            _console.print(
                f"Active Vault: [bold cyan]{vc.name}[/bold cyan] [dim]({source})[/dim]"
            )
        except Exception:
            pass
        _console.print()
        click.echo(ctx.get_help())
        return
    if ctx.invoked_subcommand not in VAULT_FREE_COMMANDS:
        ctx.obj["vault"] = get_vault(vault)


main.add_command(daily)
main.add_command(note)
main.add_command(index_cmd)
main.add_command(search_cmd)
main.add_command(tags)
main.add_command(stats)
main.add_command(vault)
main.add_command(config)
main.add_command(setup_cmd)
main.add_command(update_cmd)
main.add_command(agent)
main.add_command(consolidate)
