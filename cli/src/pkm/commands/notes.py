"""Note commands for PKM CLI."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from datetime import date
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from pkm.config import load_config
from pkm.editor import get_editor
from pkm.frontmatter import generate_frontmatter, generate_memory_frontmatter, parse, render
from pkm.wikilinks import find_backlinks

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
@click.argument("title", required=False, default=None)
@click.option("--content", default=None, help="Note content body (agent usage; title auto-generated from content)")
@click.option("--stdin", "use_stdin", is_flag=True, help="Read content from stdin")
@click.option("--type", "memory_type", type=click.Choice(["episodic", "semantic", "procedural"]), default=None)
@click.option("--importance", type=click.IntRange(1, 10), default=None)
@click.option("--session", "session_id", default=None)
@click.option("--agent", "agent_id", default=None)
@click.option("--tags", "-t", default="", help="Comma-separated tags")
@click.pass_context
def add(
    ctx: click.Context,
    title: str | None,
    content: str | None,
    use_stdin: bool,
    memory_type: str | None,
    importance: int | None,
    session_id: str | None,
    agent_id: str | None,
    tags: str,
) -> None:
    """Create a new atomic note in the vault.

    Human usage (title required):
      pkm note add "My Research Note" --tags ai

    Agent usage (--content generates title automatically):
      pkm note add --content "learned X" --type semantic --importance 7
      echo "multi-line" | pkm note add --stdin --type episodic --importance 5
    """
    if use_stdin:
        content = sys.stdin.read().strip()

    if content and not title:
        effective_title = content[:50]
    elif title:
        effective_title = title
    else:
        raise click.UsageError("Provide a title, or use --content / --stdin for agent usage")

    vault = ctx.obj["vault"]
    today = date.today().isoformat()
    slug = _slugify(effective_title)
    filename = f"{today}-{slug}.md"
    note_path: Path = vault.notes_dir / filename
    note_id = note_path.stem

    if note_path.exists():
        raise click.ClickException(f"Note already exists: {note_path}")

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    body = content or ""

    is_memory = bool(content or memory_type or importance is not None or session_id)
    if is_memory:
        from datetime import datetime, timezone
        meta = generate_memory_frontmatter(
            note_id=note_id,
            memory_type=memory_type or "semantic",
            importance=float(importance) if importance is not None else 5.0,
            created_at=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            agent_id=agent_id,
            source_type="agent",
            tags=tag_list,
        )
    else:
        meta = generate_frontmatter(note_id, tags=tag_list, aliases=[], source=today)

    note_content = render(meta, body)
    note_path.write_text(note_content, encoding="utf-8")
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

    backlink_paths = find_backlinks(vault, selected.id)
    if backlink_paths:
        console.print("\n[bold]Backlinks[/bold]")
        for bp in backlink_paths:
            try:
                bl_note = parse(bp)
                if bl_note.description:
                    console.print(f"  · {bl_note.title} — [dim]{bl_note.description}[/dim]")
                else:
                    console.print(f"  · {bl_note.title}")
            except Exception:
                pass


@note.command()
@click.argument("query")
@click.pass_context
def links(ctx: click.Context, query: str) -> None:
    """Show backlinks for a note."""
    vault = ctx.obj["vault"]
    matches = _search_notes(vault, query)
    selected = _select_note(matches, query)
    if selected is None:
        raise SystemExit(1)

    backlink_paths = find_backlinks(vault, selected.id)
    if not backlink_paths:
        console.print(f"[dim]No backlinks found for '{selected.title}'[/dim]")
        return

    table = Table(title=f"Backlinks for '{selected.title}'")
    table.add_column("Title", style="cyan")
    table.add_column("Description", style="dim")
    table.add_column("Path", style="dim")

    for bp in backlink_paths:
        try:
            bl_note = parse(bp)
            table.add_row(bl_note.title, bl_note.description or "", bp.name)
        except Exception:
            pass

    console.print(table)


from pkm.commands.maintenance import stale
from pkm.commands.links import orphans

note.add_command(stale)
note.add_command(orphans)
