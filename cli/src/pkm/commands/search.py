"""Semantic search commands for PKM CLI."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from pkm.search_engine import build_index, is_index_stale, load_index, search as search_fn

console = Console()


@click.command("index")
@click.pass_context
def index_cmd(ctx: click.Context) -> None:
    """Build the semantic search index for the vault."""
    vault = ctx.obj["vault"]
    console.print(f"[bold]Building index for vault:[/bold] {vault.name}")
    with console.status("[cyan]Loading model and encoding notes...[/cyan]"):
        vector_index = build_index(vault)
    count = len(vector_index.entries)
    console.print(f"[green]Index built:[/green] {count} note(s) indexed.")
    console.print(f"Saved to [dim]{vault.pkm_dir / 'index.json'}[/dim]")


@click.command("search")
@click.argument("query")
@click.option("--top", "-n", default=10, show_default=True, help="Number of results to return")
@click.pass_context
def search_cmd(ctx: click.Context, query: str, top: int) -> None:
    """Search vault notes semantically."""
    vault = ctx.obj["vault"]

    if is_index_stale(vault):
        console.print(
            "[yellow]Warning:[/yellow] Index may be out of date. Run 'pkm index' to rebuild."
        )

    vector_index = load_index(vault)
    results = search_fn(query, vector_index, top_n=top)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    table = Table(
        title=f'Search results for: "{query}"',
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan")
    table.add_column("Score", style="green", width=8)
    table.add_column("Backlinks", style="yellow", width=10)
    table.add_column("Tags", style="blue")

    for r in results:
        table.add_row(
            str(r.rank),
            r.title,
            f"{r.score:.4f}",
            str(r.backlink_count),
            ", ".join(r.tags) if r.tags else "",
        )

    console.print(table)
