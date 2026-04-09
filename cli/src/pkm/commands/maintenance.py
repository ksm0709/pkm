"""Maintenance commands for PKM CLI: stats, stale."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pkm.frontmatter import parse
from pkm.wikilinks import extract_links, find_orphans

console = Console()


@click.command()
@click.pass_context
def stats(ctx: click.Context) -> None:
    """Show vault statistics."""
    vault = ctx.obj["vault"]

    # Count notes
    note_count = (
        len(list(vault.notes_dir.glob("*.md"))) if vault.notes_dir.is_dir() else 0
    )

    # Count dailies
    daily_count = (
        len(list(vault.daily_dir.glob("*.md"))) if vault.daily_dir.is_dir() else 0
    )

    # Count tasks (excluding archive/)
    task_count = 0
    if vault.tasks_dir.is_dir():
        for md_file in vault.tasks_dir.glob("*.md"):
            task_count += 1

    # Count orphans
    orphan_count = len(find_orphans(vault))

    # Count unique tags
    tag_set: set[str] = set()
    dirs = [vault.notes_dir, vault.daily_dir]
    for d in dirs:
        if not d.is_dir():
            continue
        for md_file in d.glob("*.md"):
            try:
                note = parse(md_file)
                for tag in note.tags:
                    if tag:
                        tag_set.add(tag)
            except Exception:
                pass

    # Average links per note
    total_links = 0
    if vault.notes_dir.is_dir():
        for md_file in vault.notes_dir.glob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
                total_links += len(extract_links(text))
            except Exception:
                pass
    avg_links = total_links / note_count if note_count > 0 else 0.0

    # Index status
    index_path = vault.pkm_dir / "index.json"
    if index_path.exists():
        mtime = datetime.fromtimestamp(index_path.stat().st_mtime)
        index_status = f"indexed ({mtime.strftime('%Y-%m-%d %H:%M')})"
    else:
        index_status = "not indexed"

    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Notes", str(note_count))
    table.add_row("Dailies", str(daily_count))
    table.add_row("Tasks", str(task_count))
    table.add_row("Orphans", str(orphan_count))
    table.add_row("Unique tags", str(len(tag_set)))
    table.add_row("Avg links/note", f"{avg_links:.1f}")
    table.add_row("Index", index_status)

    console.print(Panel(table, title="Vault Stats", border_style="cyan"))


@click.command()
@click.option("--days", "-d", default=30, help="Days threshold")
@click.pass_context
def stale(ctx: click.Context, days: int) -> None:
    """Show notes not modified in the last N days."""
    vault = ctx.obj["vault"]

    now = time.time()
    cutoff = now - days * 86400

    stale_notes: list[tuple[Path, float]] = []

    if vault.notes_dir.is_dir():
        for md_file in vault.notes_dir.glob("*.md"):
            mtime = md_file.stat().st_mtime
            if mtime < cutoff:
                stale_notes.append((md_file, mtime))

    stale_notes.sort(key=lambda x: x[1])

    table = Table(
        title=f"Stale Notes (> {days} days)", show_header=True, header_style="bold cyan"
    )
    table.add_column("Note", style="green")
    table.add_column("Last Modified")
    table.add_column("Days Ago", justify="right")

    for md_file, mtime in stale_notes:
        last_modified = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
        days_ago = int((now - mtime) / 86400)
        table.add_row(md_file.name, last_modified, str(days_ago))

    console.print(table)
    console.print(f"\n[dim]{len(stale_notes)} stale note(s) found[/dim]")
