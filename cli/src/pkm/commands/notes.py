"""Note creation command for PKM CLI."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import click
from rich.console import Console

from pkm.frontmatter import generate_frontmatter, render

console = Console()


def _slugify(title: str) -> str:
    """Convert title to filename slug.

    For ASCII-friendly titles: lowercase, spaces to hyphens, strip non-alphanumeric except hyphens.
    For Korean-only titles that produce an empty slug: use the Korean title with spaces as hyphens.
    """
    lowered = title.lower().replace(" ", "-")
    # Keep only ASCII alphanumeric and hyphens
    ascii_slug = re.sub(r"[^a-z0-9-]", "", lowered)
    # Clean up multiple/trailing/leading hyphens
    ascii_slug = re.sub(r"-+", "-", ascii_slug).strip("-")
    if ascii_slug:
        return ascii_slug
    # Korean-only (or other non-ASCII) fallback: use title with spaces replaced by hyphens
    return title.replace(" ", "-")


@click.command()
@click.argument("title")
@click.option("--tags", "-t", default="", help="Comma-separated tags")
@click.pass_context
def new(ctx: click.Context, title: str, tags: str) -> None:
    """Create a new note in the vault."""
    vault = ctx.obj["vault"]

    today = date.today().isoformat()
    slug = _slugify(title)
    filename = f"{today}-{slug}.md"
    note_path: Path = vault.notes_dir / filename
    note_id = note_path.stem

    if note_path.exists():
        raise click.ClickException(f"Note already exists: {note_path}")

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    meta = generate_frontmatter(note_id, tags=tag_list, aliases=[], source=today)
    content = render(meta, "")

    note_path.write_text(content, encoding="utf-8")

    console.print(f"[green]Created[/green] {note_path}")
