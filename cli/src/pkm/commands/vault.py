"""Vault management commands."""

from __future__ import annotations

import os
import shutil
import subprocess
import shlex
from datetime import datetime
from pathlib import Path

import json

import click
from rich.console import Console
from rich.table import Table

from pkm.commands._trash import make_trash_path
from pkm.config import (
    VaultConfig,
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
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format",
)
def list_vaults(output_format: str) -> None:
    """List all discovered vaults."""
    from pkm.config import get_vault_context

    vaults = discover_vaults()
    if not vaults:
        if output_format == "json":
            print(json.dumps({"vaults": [], "active": None}, indent=2))
        else:
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

    if output_format == "json":
        items = []
        for name, vc in vaults.items():
            items.append(
                {
                    "name": name,
                    "type": "git" if name.startswith("@") else "local",
                    "path": str(vc.path),
                    "notes": _count_md(vc.notes_dir),
                    "dailies": _count_md(vc.daily_dir),
                    "active": name == active_name,
                }
            )
        print(
            json.dumps(
                {
                    "vaults": items,
                    "active": active_name,
                    "active_source": active_source,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
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
                active_mark = (
                    f"[bold green]★[/bold green] [dim]via {active_source}[/dim]"
                )
            else:
                active_mark = ""
            vault_type = "[cyan]git[/cyan]" if name.startswith("@") else "local"
            table.add_row(
                name,
                vault_type,
                str(vc.path),
                str(notes_count),
                str(dailies_count),
                active_mark,
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
    """Show the currently active vault path."""
    from pkm.config import get_vault_context

    try:
        vc, _source = get_vault_context()
        click.echo(str(vc.path))
    except click.ClickException:
        pass


@vault.command()
@click.argument("name", required=False)
def edit(name: str | None) -> None:
    """Open the vault in the configured editor."""
    from pkm.config import get_vault_context, discover_vaults

    if name:
        vaults = discover_vaults()
        if name not in vaults:
            raise click.ClickException(f"Vault '{name}' not found.")
        vc = vaults[name]
    else:
        vc, _ = get_vault_context()

    editor_cmd = load_config().get("editor") or os.environ.get("EDITOR", "vim")
    subprocess.run([*shlex.split(editor_cmd), str(vc.path)])


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

    trash_path = make_trash_path(name)
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
            "This directory is already set up as a vault (.pkm exists). "
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
    console.print(
        f"[green]✔[/green] Created vault [bold]{final_name}[/bold] at {vault_path}"
    )
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


@vault.command()
@click.option(
    "--remove",
    is_flag=True,
    default=False,
    help="Remove the vault instead of migrating to root vault.",
)
def unset(remove: bool) -> None:
    """Unset the current directory's vault and optionally migrate contents."""
    from pkm.config import get_parent_vault, get_vault_context

    cwd = Path.cwd()
    pkm_file = cwd / ".pkm"

    if not pkm_file.exists():
        raise click.ClickException("No .pkm file found in the current directory.")

    try:
        vc, _ = get_vault_context()
    except click.ClickException as e:
        raise click.ClickException(f"Failed to resolve current vault: {e}")

    if remove:
        trash_path = make_trash_path(vc.name)
        if vc.path.exists():
            shutil.move(str(vc.path), str(trash_path))
            console.print(f"[yellow]Moved vault to trash:[/yellow] {trash_path}")

        pkm_file.unlink()
        console.print(
            f"[green]✔[/green] Removed vault [bold]{vc.name}[/bold] and deleted .pkm"
        )
        return

    parent_vc = get_parent_vault(cwd)
    if not parent_vc:
        raise click.ClickException(
            "No root vault (.pkm in parent directories) found to migrate to. "
            "Use --remove to just remove the vault without migration."
        )

    console.print(
        f"Migrating vault [bold]{vc.name}[/bold] to root vault [bold]{parent_vc.name}[/bold]..."
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    subdirs = ["daily", "notes", "tags", "tasks", "data", ".pkm/artifacts"]

    for subdir in subdirs:
        src_dir = vc.path / subdir
        if not src_dir.exists():
            continue

        dst_dir = parent_vc.path / subdir
        dst_dir.mkdir(parents=True, exist_ok=True)

        for root, _, files in os.walk(src_dir):
            rel_root = Path(root).relative_to(src_dir)
            target_dir = dst_dir / rel_root
            target_dir.mkdir(parents=True, exist_ok=True)

            for file in files:
                src_file = Path(root) / file
                dst_file = target_dir / file

                if dst_file.exists() and subdir == "daily" and file.endswith(".md"):
                    # Merge daily notes: union tags, deduplicate + time-sort entries
                    _merge_daily_notes(dst_file, src_file)
                    src_file.unlink()
                elif dst_file.exists():
                    dst_file = (
                        target_dir
                        / f"{src_file.stem}_migrated_{timestamp}{src_file.suffix}"
                    )
                    shutil.move(str(src_file), str(dst_file))
                else:
                    shutil.move(str(src_file), str(dst_file))

    trash_path = make_trash_path(vc.name)
    if vc.path.exists():
        shutil.move(str(vc.path), str(trash_path))

    pkm_file.unlink()
    console.print("[green]✔[/green] Migrated vault contents and deleted .pkm")
    console.print(
        f"[yellow]Moved original vault directory to trash:[/yellow] {trash_path}"
    )


def _merge_daily_notes(dst_file: Path, src_file: Path) -> None:
    """Merge two daily note files: union tags, deduplicate + time-sort entries."""
    from pkm.frontmatter import parse as parse_note, render

    dst_note = parse_note(dst_file)
    src_note = parse_note(src_file)

    # Merge tags (union, deduplicated, preserve order)
    seen: set[str] = set()
    merged_tags: list[str] = []
    for tag in dst_note.tags + src_note.tags:
        if tag and tag not in seen:
            seen.add(tag)
            merged_tags.append(tag)

    # Merge frontmatter: dst takes precedence, add missing keys from src
    merged_meta = dict(src_note.meta)
    merged_meta.update(dst_note.meta)
    merged_meta["tags"] = merged_tags

    # Parse body lines into entries and non-entries
    def _parse_body(body: str) -> tuple[list[str], list[str]]:
        entries: list[str] = []
        other: list[str] = []
        for line in body.strip().splitlines():
            stripped = line.strip()
            if stripped.startswith("- ["):
                entries.append(stripped)
            elif stripped:
                other.append(stripped)
        return entries, other

    dst_entries, dst_other = _parse_body(dst_note.body)
    src_entries, src_other = _parse_body(src_note.body)

    # Deduplicate entries
    all_entries = list(dict.fromkeys(dst_entries + src_entries))

    # Sort by timestamp (extract [HH:MM] prefix)
    import re

    def _sort_key(entry: str) -> str:
        m = re.match(r"- \[(\d{2}:\d{2})\]", entry)
        return m.group(1) if m else "99:99"

    all_entries.sort(key=_sort_key)

    # Merge non-entry lines (deduplicated)
    all_other = list(dict.fromkeys(dst_other + src_other))

    # Reconstruct body
    body_parts = all_entries
    if all_other:
        body_parts = body_parts + [""] + all_other

    merged_body = "\n".join(body_parts) + "\n"
    dst_file.write_text(render(merged_meta, merged_body), encoding="utf-8")


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
