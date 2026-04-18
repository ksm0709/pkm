"""PKM CLI entrypoint."""

from __future__ import annotations

import click
from rich.console import Console

from pkm import __version__
from pkm.version_check import available_update
from pkm.commands.config import config
from pkm.commands.daily import daily
from pkm.commands.notes import note
from pkm.commands.maintenance import stats
from pkm.commands.tag_commands import tags
from pkm.commands.search import index_cmd, search_cmd
from pkm.commands.setup import setup_cmd
from pkm.commands.agent import agent
from pkm.commands.hook import hook as hook_group
from pkm.commands.consolidate import consolidate
from pkm.commands.update import update_cmd
from pkm.commands.vault import vault
from pkm.commands.data import data
from pkm.commands.daemon import daemon_group
from pkm.commands.mcp import mcp_cmd
from pkm.config import get_vault

VAULT_FREE_COMMANDS = {"vault", "config", "setup", "update", "hook", "daemon", "mcp"}

_console = Console()


def print_version(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    _console.print(f"[bold]pkm[/bold] v{__version__} — Personal Knowledge Management CLI\n")
    try:
        from pkm.changelog import get_changelog
        cl = get_changelog(latest_n=3)
        if cl:
            from rich.markdown import Markdown
            _console.print(Markdown(cl))
    except Exception:
        pass
    ctx.exit()

@click.group(invoke_without_command=True)
@click.option("--vault", "-v", default=None, help="Vault name (default: auto-detected)")
@click.option("--version", is_flag=True, callback=print_version, expose_value=False, is_eager=True, help="Show the version and latest changelog")
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
main.add_command(hook_group, name="hook")
main.add_command(consolidate)
main.add_command(data)
main.add_command(daemon_group, name="daemon")
main.add_command(mcp_cmd)
