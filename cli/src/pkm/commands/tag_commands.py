"""Tag index note commands for PKM CLI."""

from __future__ import annotations

import fnmatch
import json
import re
from collections import Counter
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pkm.config import VaultConfig
from pkm.frontmatter import generate_frontmatter, parse, render

console = Console()


def ensure_tag_note(vault: VaultConfig, tag_name: str) -> Path:
    """Ensure a tag note exists in tags/ dir, creating it lazily if needed."""
    if not re.match(r"^[\w\-. ]+$", tag_name):
        raise click.BadParameter(f"Invalid tag name: {tag_name!r}")
    tag_path = (vault.tags_dir / f"{tag_name}.md").resolve()
    if not str(tag_path).startswith(str(vault.tags_dir.resolve())):
        raise click.BadParameter(f"Invalid tag name: {tag_name!r}")
    if tag_path.exists():
        return tag_path
    vault.tags_dir.mkdir(parents=True, exist_ok=True)
    meta = generate_frontmatter(note_id=tag_name, tags=[])
    content = render(meta, "")
    tag_path.write_text(content, encoding="utf-8")
    return tag_path


def _collect_notes_with_tag(vault: VaultConfig, tag: str) -> list:
    """Find all notes in notes/ and daily/ that have the given tag."""
    results = []
    for d in (vault.notes_dir, vault.daily_dir):
        if not d.is_dir():
            continue
        for md_file in sorted(d.glob("*.md")):
            try:
                note = parse(md_file)
                if tag in note.tags:
                    results.append(note)
            except Exception:
                pass
    return results


def count_all_tags(vault: VaultConfig) -> list[tuple[str, int]]:
    """Scan notes_dir and daily_dir and return all non-empty tags sorted by count."""
    tag_counter: Counter[str] = Counter()
    for d in (vault.notes_dir, vault.daily_dir):
        if not d.is_dir():
            continue
        for md_file in d.glob("*.md"):
            try:
                note = parse(md_file)
                tag_counter.update(tag for tag in note.tags if tag)
            except Exception:
                pass
    return tag_counter.most_common()


def search_by_tag_pattern(vault: VaultConfig, pattern: str) -> tuple[str, list]:
    """Return (mode_label, matched_notes) for the given tag search pattern."""
    all_notes = []
    for d in (vault.notes_dir, vault.daily_dir):
        if not d.is_dir():
            continue
        for md_file in sorted(d.glob("*.md")):
            try:
                note = parse(md_file)
                if note.tags:
                    all_notes.append(note)
            except Exception:
                pass

    # Single + is AND operator (but ++ in tag names like c++ is preserved)
    and_parts = re.split(r"(?<!\+)\+(?!\+)", pattern)
    if len(and_parts) > 1:
        required_tags = [t.strip() for t in and_parts if t.strip()]
        matched = [n for n in all_notes if all(t in n.tags for t in required_tags)]
        mode = f"AND({', '.join(required_tags)})"
    elif "," in pattern:
        or_tags = [t.strip() for t in pattern.split(",") if t.strip()]
        matched = [n for n in all_notes if any(t in n.tags for t in or_tags)]
        mode = f"OR({', '.join(or_tags)})"
    elif "*" in pattern or "?" in pattern:
        matched = [
            n for n in all_notes if any(fnmatch.fnmatch(t, pattern) for t in n.tags)
        ]
        mode = f"glob({pattern})"
    else:
        matched = [n for n in all_notes if pattern in n.tags]
        mode = f"exact({pattern})"

    return mode, matched


@click.group(invoke_without_command=True)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format",
)
@click.pass_context
def tags(ctx: click.Context, output_format: str) -> None:
    """Show all tags used across notes and dailies, sorted by count."""
    if ctx.invoked_subcommand is not None:
        return

    vault = ctx.obj["vault"]
    tag_counts = count_all_tags(vault)

    if output_format == "json":
        items = [{"tag": tag, "count": count} for tag, count in tag_counts]
        print(
            json.dumps(
                {"tags": items, "count": len(items)}, ensure_ascii=False, indent=2
            )
        )
    else:
        table = Table(title="Tags", show_header=True, header_style="bold cyan")
        table.add_column("Tag", style="green")
        table.add_column("Count", justify="right")

        for tag, count in tag_counts:
            table.add_row(tag, str(count))

        console.print(table)


@tags.command()
@click.argument("tag")
@click.pass_context
def edit(ctx: click.Context, tag: str) -> None:
    """Open a tag note in the editor."""
    import shlex
    import subprocess

    from pkm.config import load_config
    from pkm.editor import get_editor

    vault = ctx.obj["vault"]
    tag_path = ensure_tag_note(vault, tag)
    config_data = load_config()
    editor_cmd = get_editor(config_data)
    result = subprocess.run([*shlex.split(editor_cmd), str(tag_path)])
    if result.returncode != 0:
        console.print(f"[yellow]Editor exited with code {result.returncode}[/yellow]")


@tags.command()
@click.argument("tag")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format",
)
@click.pass_context
def show(ctx: click.Context, tag: str, output_format: str) -> None:
    """Show a tag note and all notes with that tag."""
    vault = ctx.obj["vault"]

    tag_path = ensure_tag_note(vault, tag)
    tag_note = parse(tag_path)
    notes = _collect_notes_with_tag(vault, tag)

    if output_format == "json":
        items = [
            {"title": n.title, "description": n.description or "", "path": n.path.name}
            for n in notes
        ]
        print(
            json.dumps(
                {
                    "tag": tag,
                    "description": tag_note.description or "",
                    "body": tag_note.body.strip(),
                    "notes": items,
                    "count": len(items),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        header = f"Tag: {tag}"
        if tag_note.description:
            header += f" — {tag_note.description}"

        body = tag_note.body.strip()
        if body:
            console.print(Panel(body, title=header, border_style="green"))
        else:
            console.print(
                Panel(
                    "[dim]No description yet. Edit with: pkm tags edit "
                    + tag
                    + "[/dim]",
                    title=header,
                    border_style="green",
                )
            )

        if not notes:
            console.print(f"\n[dim]No notes found with tag '{tag}'[/dim]")
            return

        table = Table(
            title=f"Notes tagged '{tag}'", show_header=True, header_style="bold cyan"
        )
        table.add_column("Title", style="cyan")
        table.add_column("Description", style="dim")
        table.add_column("Path", style="dim")

        for n in notes:
            table.add_row(n.title, n.description or "", n.path.name)

        console.print(table)


@tags.command()
@click.argument("pattern")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format",
)
@click.pass_context
def search(ctx: click.Context, pattern: str, output_format: str) -> None:
    """Search notes by tag pattern. Supports glob (*), AND (+), and OR (,)."""
    vault = ctx.obj["vault"]

    mode, matched = search_by_tag_pattern(vault, pattern)

    if output_format == "json":
        items = [
            {"title": n.title, "tags": n.tags, "path": n.path.name} for n in matched
        ]
        print(
            json.dumps(
                {
                    "pattern": pattern,
                    "mode": mode,
                    "results": items,
                    "count": len(items),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if not matched:
            console.print(f"[dim]No notes found matching {mode}[/dim]")
            return

        table = Table(
            title=f"Tag Search: {mode}", show_header=True, header_style="bold cyan"
        )
        table.add_column("Title", style="cyan")
        table.add_column("Tags", style="green")
        table.add_column("Path", style="dim")

        for n in matched:
            table.add_row(n.title, ", ".join(n.tags), n.path.name)

        console.print(table)
        console.print(f"\n[dim]{len(matched)} note(s) found[/dim]")
