"""Fresh-process post-update synchronization for installed PKM assets."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import click
from rich.console import Console

console = Console()
_T = TypeVar("_T")


def _run_sync(label: str, sync: Callable[[], _T]) -> _T:
    try:
        return sync()
    except Exception as exc:
        raise click.ClickException(f"Post-update {label} sync failed: {exc}") from exc


@click.command("post-update", hidden=True)
@click.option("--from-version", required=True, metavar="VERSION")
def post_update_cmd(from_version: str) -> None:
    """Synchronize installed assets after an updater process replaces pkm."""
    # Resolve these imports in this newly installed process. The updater that
    # launched us may still have the previous package loaded in memory.
    from pkm.commands.setup import (
        install_shell_aliases,
        install_skill_files,
        sync_existing_web_unit,
    )
    from pkm.workflows import sync_installed_workflow_defaults

    skills_installed = _run_sync("skill files", install_skill_files)
    if not skills_installed:
        raise click.ClickException(
            "Post-update skill files sync failed: bundled PKM skill assets were not found."
        )
    _run_sync("shell aliases", install_shell_aliases)

    unit_path = _run_sync("PKM web unit", sync_existing_web_unit)
    if unit_path is not None:
        console.print(f"[green]✓ PKM web unit synced:[/green] {unit_path}")

    workflow_path = _run_sync(
        "workflow settings", sync_installed_workflow_defaults
    )
    if workflow_path is not None:
        console.print(
            f"[green]✓ PKM workflow settings synced:[/green] {workflow_path}"
        )

    console.print(
        "[green]✓ Post-update synchronization complete[/green] "
        f"[dim](from v{from_version.removeprefix('v')})[/dim]"
    )
