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
    discover_vaults,
    get_vaults_root,
    load_config,
    save_config,
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
# 진행 중인 일

## 🔴 진행 중 (WIP)

## 🟡 예정 (TODO)

## ✅ 이번 주 완료

## ⏸ 보류

---
_태스크 상세: `tasks/task-<slug>.md` | 완료 태스크: `tasks/archive/`_
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
