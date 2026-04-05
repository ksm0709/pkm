"""Link analysis commands for PKM CLI."""

from __future__ import annotations

import re
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from pkm.wikilinks import find_orphans

console = Console()


@click.command()
@click.pass_context
def orphans(ctx: click.Context) -> None:
    """List orphan notes — notes with no inbound or outbound links."""
    vault = ctx.obj["vault"]
    orphan_paths = find_orphans(vault)

    if not orphan_paths:
        console.print("[green]No orphan notes found.[/green]")
        return

    table = Table(title="Orphan Notes", show_header=True, header_style="bold magenta")
    table.add_column("Filename", style="cyan")
    table.add_column("Tags", style="yellow")

    for path in orphan_paths:
        filename = path.name
        # Extract tags from frontmatter if present
        tags = _extract_tags(path)
        table.add_row(filename, ", ".join(tags) if tags else "")

    console.print(table)
    console.print(f"\n[bold]{len(orphan_paths)}[/bold] orphan note(s) found.")


def _extract_tags(path: Path) -> list[str]:
    """Extract tags list from frontmatter of a note file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    # Match YAML frontmatter block
    fm_match = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
    if not fm_match:
        return []

    fm_text = fm_match.group(1)

    # Try to parse tags: [a, b] inline style
    inline = re.search(r'^tags:\s*\[([^\]]*)\]', fm_text, re.MULTILINE)
    if inline:
        raw = inline.group(1)
        return [t.strip() for t in raw.split(',') if t.strip()]

    # Try block style tags:
    #   tags:
    #     - a
    block = re.search(r'^tags:\s*\n((?:  - .+\n?)*)', fm_text, re.MULTILINE)
    if block:
        return re.findall(r'  - (.+)', block.group(1))

    return []
