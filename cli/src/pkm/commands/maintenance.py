"""Maintenance commands for PKM CLI: stats, stale."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pkm.config import VaultConfig
from pkm.frontmatter import parse
from pkm.wikilinks import extract_links, find_orphans

console = Console()


def compute_vault_stats(vault: VaultConfig) -> dict:
    """Compute vault statistics and return them as a dict."""
    # Count notes
    note_count = (
        len(list(vault.notes_dir.glob("*.md"))) if vault.notes_dir.is_dir() else 0
    )

    # Count dailies
    daily_count = (
        len(list(vault.daily_dir.glob("*.md"))) if vault.daily_dir.is_dir() else 0
    )

    # Count orphans
    orphan_count = len(find_orphans(vault))

    # Count unique tags
    tag_set: set[str] = set()
    for d in (vault.notes_dir, vault.daily_dir):
        if not d.is_dir():
            continue
        for md_file in d.glob("*.md"):
            try:
                note = parse(md_file)
                tag_set.update(tag for tag in note.tags if tag)
            except Exception:
                pass

    # Average links per note
    total_links = 0
    if vault.notes_dir.is_dir():
        for md_file in vault.notes_dir.glob("*.md"):
            try:
                total_links += len(extract_links(md_file.read_text(encoding="utf-8")))
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

    return {
        "notes": note_count,
        "dailies": daily_count,
        "orphans": orphan_count,
        "unique_tags": len(tag_set),
        "avg_links_per_note": round(avg_links, 1),
        "index": index_status,
    }


def list_stale(vault: VaultConfig, days: int) -> list[dict]:
    """Return stale notes as a list of dicts, sorted oldest-first."""
    now = time.time()
    cutoff = now - days * 86400

    stale_notes: list[tuple[Path, float]] = []

    if vault.notes_dir.is_dir():
        for md_file in vault.notes_dir.glob("*.md"):
            mtime = md_file.stat().st_mtime
            if mtime < cutoff:
                stale_notes.append((md_file, mtime))

    stale_notes.sort(key=lambda x: x[1])

    return [
        {
            "note": md_file.name,
            "last_modified": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d"),
            "days_ago": int((now - mtime) / 86400),
        }
        for md_file, mtime in stale_notes
    ]


@click.command()
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format",
)
@click.pass_context
def stats(ctx: click.Context, output_format: str) -> None:
    """Show vault statistics."""
    vault = ctx.obj["vault"]
    data = compute_vault_stats(vault)

    if output_format == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        table = Table(show_header=False, box=None)
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        table.add_row("Notes", str(data["notes"]))
        table.add_row("Dailies", str(data["dailies"]))
        table.add_row("Tasks", str(data["tasks"]))
        table.add_row("Orphans", str(data["orphans"]))
        table.add_row("Unique tags", str(data["unique_tags"]))
        table.add_row("Avg links/note", f"{data['avg_links_per_note']:.1f}")
        table.add_row("Index", data["index"])

        console.print(Panel(table, title="Vault Stats", border_style="cyan"))


@click.command()
@click.option("--days", "-d", default=30, help="Days threshold")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format",
)
@click.pass_context
def stale(ctx: click.Context, days: int, output_format: str) -> None:
    """Show notes not modified in the last N days."""
    vault = ctx.obj["vault"]
    items = list_stale(vault, days)

    if output_format == "json":
        print(
            json.dumps(
                {"threshold_days": days, "stale_notes": items, "count": len(items)},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        table = Table(
            title=f"Stale Notes (> {days} days)",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Note", style="green")
        table.add_column("Last Modified")
        table.add_column("Days Ago", justify="right")

        for item in items:
            table.add_row(item["note"], item["last_modified"], str(item["days_ago"]))

        console.print(table)
        console.print(f"\n[dim]{len(items)} stale note(s) found[/dim]")
