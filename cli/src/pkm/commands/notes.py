"""Note commands for PKM CLI."""

from __future__ import annotations

import re
import shlex
import subprocess
from datetime import date
from pathlib import Path

import click
from rich.console import Console

from pkm.config import load_config
from pkm.editor import get_editor
from pkm.frontmatter import generate_frontmatter, parse, render

console = Console()


def _slugify(title: str) -> str:
    """Convert title to filename slug."""
    lowered = title.lower().replace(" ", "-")
    ascii_slug = re.sub(r"[^a-z0-9-]", "", lowered)
    ascii_slug = re.sub(r"-+", "-", ascii_slug).strip("-")
    if ascii_slug:
        return ascii_slug
    return title.replace(" ", "-")


def _search_notes(vault, query: str) -> list:
    """Search notes by title (partial match, case-insensitive)."""
    if not vault.notes_dir.is_dir():
        return []
    query_lower = query.lower()
    matches = []
    for md_file in sorted(vault.notes_dir.glob("*.md")):
        try:
            note = parse(md_file)
            if query_lower in note.title.lower():
                matches.append(note)
        except Exception:
            pass
    return matches


def _select_note(matches: list, query: str):
    """Handle zero/single/multi match selection. Returns Note or None."""
    if not matches:
        console.print(f"[red]No notes found matching '{query}'[/red]")
        return None
    if len(matches) == 1:
        return matches[0]
    console.print(f"[yellow]Found {len(matches)} notes matching '{query}':[/yellow]")
    for i, n in enumerate(matches, 1):
        console.print(f"  {i}. {n.title}  [dim]({n.path.name})[/dim]")
    choice = click.prompt("Select note number", type=int)
    if choice < 1 or choice > len(matches):
        console.print("[red]Invalid selection[/red]")
        return None
    return matches[choice - 1]


@click.group(invoke_without_command=True)
@click.pass_context
def note(ctx: click.Context) -> None:
    """Manage notes."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@note.command()
@click.argument("title")
@click.option("--tags", "-t", default="", help="Comma-separated tags")
@click.pass_context
def add(ctx: click.Context, title: str, tags: str) -> None:
    """Create a new atomic note in the vault."""
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


@note.command()
@click.argument("query")
@click.pass_context
def edit(ctx: click.Context, query: str) -> None:
    """Open a note in the editor (search by title)."""
    vault = ctx.obj["vault"]
    matches = _search_notes(vault, query)
    selected = _select_note(matches, query)
    if selected is None:
        raise SystemExit(1)
    config_data = load_config()
    editor_cmd = get_editor(config_data)
    result = subprocess.run([*shlex.split(editor_cmd), str(selected.path)])
    if result.returncode != 0:
        console.print(f"[yellow]Editor exited with code {result.returncode}[/yellow]")


@note.command()
@click.argument("query")
@click.pass_context
def show(ctx: click.Context, query: str) -> None:
    """Show note contents in the terminal (search by title)."""
    vault = ctx.obj["vault"]
    matches = _search_notes(vault, query)
    selected = _select_note(matches, query)
    if selected is None:
        raise SystemExit(1)
    console.print(selected.path.read_text(encoding="utf-8"), end="")


from pkm.commands.maintenance import stale
from pkm.commands.links import orphans

note.add_command(stale)
note.add_command(orphans)
