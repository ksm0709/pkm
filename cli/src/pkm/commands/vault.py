"""Vault management commands."""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from pkm.config import (
    VaultConfig,
    VaultSuggestion,
    discover_vaults,
    get_vaults_root,
    load_config,
    save_config,
    suggest_vault_name,
)

console = Console()

ONGOING_TEMPLATE = """\
---
id: {name}-ongoing-tasks
aliases:
  - ongoing
tags:
  - tasks
  - ongoing
---
# In Progress

## 🔴 In Progress (WIP)

## 🟡 Upcoming (TODO)

## ✅ Completed This Week

## ⏸ On Hold

---
_Task details: `tasks/task-<slug>.md` | Completed tasks: `tasks/archive/`_
"""


@click.group()
def vault() -> None:
    """Manage vaults."""


@vault.command(name="list")
def list_vaults() -> None:
    """List all discovered vaults."""
    from pkm.config import get_vault_context

    vaults = discover_vaults()
    if not vaults:
        console.print(
            "No vaults found. Use [bold]pkm vault add <name>[/bold] to create one."
        )
        return

    try:
        active_vault, active_source = get_vault_context()
        active_name = active_vault.name
    except click.ClickException:
        active_name = None
        active_source = ""

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Path")
    table.add_column("Notes", justify="right")
    table.add_column("Dailies", justify="right")
    table.add_column("Active", justify="left")

    for name, vc in vaults.items():
        notes_count = _count_md(vc.notes_dir)
        dailies_count = _count_md(vc.daily_dir)
        if name == active_name:
            active_mark = f"[bold green]★[/bold green] [dim]via {active_source}[/dim]"
        else:
            active_mark = ""
        vault_type = "[cyan]git[/cyan]" if name.startswith("@") else "local"
        table.add_row(
            name, vault_type, str(vc.path), str(notes_count), str(dailies_count), active_mark
        )

    console.print(table)


def init_vault_dirs(vault_path: Path, name: str) -> None:
    """Create standard vault directory structure and ongoing.md template."""
    dirs = [
        vault_path / "daily",
        vault_path / "notes",
        vault_path / "tags",
        vault_path / "tasks" / "archive",
        vault_path / "data",
        vault_path / ".pkm" / "artifacts",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    ongoing = vault_path / "tasks" / "ongoing.md"
    if not ongoing.exists():
        ongoing.write_text(ONGOING_TEMPLATE.format(name=name), encoding="utf-8")


@vault.command()
def where() -> None:
    """Show the currently active vault name and path."""
    from pkm.config import get_vault_context

    try:
        vc, _source = get_vault_context()
        click.echo(vc.name)
        click.echo(str(vc.path))
    except click.ClickException:
        click.echo("No vault detected. Run 'pkm vault list' to see available vaults.")


@vault.command()
@click.argument("name")
def add(name: str) -> None:
    """Create a new vault."""
    if not name or "/" in name or "\\" in name:
        raise click.ClickException(
            f"Invalid vault name '{name}': must be non-empty and contain no slashes."
        )

    vault_path = get_vaults_root() / name
    if vault_path.exists():
        raise click.ClickException(f"Vault '{name}' already exists at {vault_path}")

    init_vault_dirs(vault_path, name)
    console.print(f"[green]Created vault '{name}'[/green] at {vault_path}")


@vault.command()
@click.argument("name")
@click.option(
    "--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt."
)
def remove(name: str, yes: bool) -> None:
    """Remove a vault by moving it to trash."""
    vaults = discover_vaults()
    if name not in vaults:
        raise click.ClickException(f"Vault '{name}' not found.")

    vc = vaults[name]
    vault_path = vc.path
    notes_count = _count_md(vc.notes_dir)
    dailies_count = _count_md(vc.daily_dir)

    console.print(
        f"Vault [bold]{name}[/bold]: {notes_count} notes, {dailies_count} dailies"
    )

    if not yes:
        click.confirm(f"Move vault '{name}' to trash?", abort=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    trash_parent = Path.home() / ".local" / "share" / "pkm" / "trash"
    trash_path = trash_parent / f"{name}-{timestamp}"
    trash_parent.mkdir(parents=True, exist_ok=True)

    shutil.move(str(vault_path), str(trash_path))
    console.print(f"[yellow]Moved to trash:[/yellow] {trash_path}")


@vault.command()
@click.argument("name")
def open(name: str) -> None:
    """Switch the active vault (set as default)."""
    vaults = discover_vaults()
    if name not in vaults:
        raise click.ClickException(
            f"Vault '{name}' not found. Available: {', '.join(vaults) or 'none'}"
        )
    data = dict(load_config())
    data["defaults"] = dict(data.get("defaults", {}))
    data["defaults"]["vault"] = name
    save_config(data)
    console.print(f"[green]★ Switched to vault '{name}'[/green]")


@vault.command()
def setup() -> None:
    """Declare the current directory as a PKM vault."""
    from pathlib import Path

    cwd = Path.cwd()
    pkm_file = cwd / ".pkm"

    if pkm_file.exists():
        raise click.ClickException(
            f"This directory is already set up as a vault (.pkm exists). "
            "Run 'pkm vault list' to see all configured vaults."
        )

    suggestion = suggest_vault_name(cwd=cwd)

    final_name = click.prompt(
        f"Suggested vault name: {suggestion.name}\nPress Enter to confirm or type a new name",
        default=suggestion.name,
    )

    # Create vault directory structure
    vault_path = get_vaults_root() / final_name
    init_vault_dirs(vault_path, final_name)

    # Write .pkm in current directory
    pkm_file.write_text(f'vault = "{final_name}"\n', encoding="utf-8")
    console.print(f"[green]✔[/green] Created vault [bold]{final_name}[/bold] at {vault_path}")
    console.print(f"[green]✔[/green] Written .pkm in {cwd}")

    # Side effect: ensure repo root has a .pkm if we're in a subdir
    if suggestion.is_subdir and suggestion.git_root is not None:
        root_pkm = suggestion.git_root / ".pkm"
        if not root_pkm.exists():
            root_suggestion = suggest_vault_name(cwd=suggestion.git_root)
            root_name = root_suggestion.name
            root_pkm.write_text(f'vault = "{root_name}"\n', encoding="utf-8")
            console.print(
                f"[green]✔[/green] Also created .pkm at repo root: "
                f"{suggestion.git_root} (vault={root_name})"
            )

    console.print(
        "[dim]Tip: commit .pkm to share vault mapping with your team, "
        "or add to .gitignore for personal use.[/dim]"
    )


def _count_md(directory: Path) -> int:
    if not directory.exists():
        return 0
    return sum(1 for _ in directory.glob("*.md"))


def _default_vault_name(vaults: dict[str, VaultConfig]) -> str | None:
    env_default = os.environ.get("PKM_DEFAULT_VAULT")
    if env_default and env_default in vaults:
        return env_default
    config_default = load_config().get("defaults", {}).get("vault")
    if config_default and config_default in vaults:
        return config_default
    return next(iter(vaults), None)
