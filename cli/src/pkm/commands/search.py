"""Semantic search commands for PKM CLI."""

from __future__ import annotations

from pathlib import Path

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
@click.option("--type", "memory_type", type=click.Choice(["episodic", "semantic", "procedural"]), default=None, help="Filter by memory type")
@click.option("--min-importance", type=click.FloatRange(1, 10), default=1.0, help="Minimum importance score")
@click.option("--recency-weight", type=click.FloatRange(0, 1), default=0.0, help="Weight for recency+importance scoring (0=pure semantic)")
@click.option("--session", "session_id", default=None, help="Filter by session ID")
@click.pass_context
def search_cmd(
    ctx: click.Context,
    query: str,
    top: int,
    memory_type: str | None,
    min_importance: float,
    recency_weight: float,
    session_id: str | None,
) -> None:
    """Search vault notes semantically.

    Memory filters:
      pkm search "error" --type procedural --min-importance 5
      pkm search "session work" --session abc123
      pkm search "recent" --recency-weight 0.4
    """
    vault = ctx.obj["vault"]

    if is_index_stale(vault):
        console.print(
            "[yellow]Warning:[/yellow] Index may be out of date. Run 'pkm index' to rebuild."
        )

    vector_index = load_index(vault)
    results = search_fn(
        query,
        vector_index,
        top_n=top,
        memory_type_filter=memory_type,
        min_importance=min_importance,
        recency_weight=recency_weight,
    )

    # Apply session filter post-search (frontmatter scan)
    if session_id:
        import yaml
        filtered = []
        for r in results:
            try:
                text = Path(r.path).read_text(encoding="utf-8")
                if not text.startswith("---"):
                    continue
                end = text.find("---", 3)
                if end == -1:
                    continue
                fm = yaml.safe_load(text[3:end]) or {}
                if fm.get("session_id") == session_id:
                    filtered.append(r)
            except Exception:
                pass
        results = filtered

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
    table.add_column("Type", style="magenta", width=10)
    table.add_column("Imp", style="yellow", width=4)
    table.add_column("Tags", style="blue")

    for r in results:
        mt = getattr(r, "memory_type", None) or ""
        imp = getattr(r, "importance", None)
        imp_str = f"{imp:.0f}" if imp is not None else ""
        table.add_row(
            str(r.rank),
            r.title,
            f"{r.score:.4f}",
            mt,
            imp_str,
            ", ".join(r.tags) if r.tags else "",
        )

    console.print(table)
