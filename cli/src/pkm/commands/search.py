"""Semantic search commands for PKM CLI."""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from pkm.search_engine import (
    build_index,
    is_index_stale,
    load_index,
    search as search_fn,
    search_via_daemon,
)

console = Console()


def _get_description(result) -> str | None:
    """Extract description from frontmatter or first 200 chars of body."""
    try:
        from pkm.frontmatter import parse as parse_note

        note = parse_note(Path(result.path))
        desc = note.meta.get("description")
        if desc:
            return str(desc)
        body = note.body.strip()
        if body:
            return body[:200]
    except Exception:
        pass
    return None


def format_search_results(
    query: str,
    results: list,
    output_format: str,
    console: Console,
    vault=None,
    stale_warning: str | None = None,
) -> None:
    """Shared helper to format and print search results as JSON or table."""
    if output_format == "json":
        items = []
        for r in results:
            items.append(
                {
                    "rank": r.rank,
                    "title": r.title,
                    "description": _get_description(r),
                    "score": round(r.score, 6),
                    "importance": getattr(r, "importance", None),
                    "memory_type": getattr(r, "memory_type", None),
                    "tags": r.tags if r.tags else [],
                    "note_id": r.note_id,
                    "graph_context": getattr(r, "graph_context", None),
                }
            )
        payload: dict = {
            "query": query,
            "result_count": len(results),
            "results": items,
        }
        if stale_warning:
            payload["warning"] = stale_warning
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("")
        print("* Next: pkm note show <title>  — open a specific note")
        print(
            "* Search more: pkm search <keyword>  (add --top N to change result count)"
        )
        print("* Save insight: pkm note add --content '<insight>' --type semantic")
    else:
        if stale_warning:
            console.print(f"[yellow]Warning:[/yellow] {stale_warning}")
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
        table.add_column("Description", style="dim", max_width=40, no_wrap=True)
        table.add_column("Score", style="green", width=8)
        table.add_column("Type", style="magenta", width=10)
        table.add_column("Imp", style="yellow", width=4)
        table.add_column("Tags", style="blue")

        for r in results:
            mt = getattr(r, "memory_type", None) or ""
            imp = getattr(r, "importance", None)
            imp_str = f"{imp:.0f}" if imp is not None else ""
            desc = _get_description(r) or ""
            if len(desc) > 40:
                desc = desc[:37] + "..."
            table.add_row(
                str(r.rank),
                r.title,
                desc,
                f"{r.score:.4f}",
                mt,
                imp_str,
                ", ".join(r.tags) if r.tags else "",
            )
        console.print(table)


@click.command("index")
@click.pass_context
def index_cmd(ctx: click.Context) -> None:
    """Build the semantic search index for the vault."""
    vault = ctx.obj["vault"]
    console.print(f"[bold]Building index for vault:[/bold] {vault.name}")
    with console.status("[cyan]Loading model and encoding notes...[/cyan]"):
        vector_index = build_index(vault)
    count = len(vector_index.entries)
    console.print(f"[green]✓ AST cache updated[/green] [dim]({vault.pkm_dir / 'ast.db'})[/dim]")
    console.print(f"[green]✓ Structural graph built[/green] [dim]({vault.pkm_dir / 'graph.json'})[/dim]")
    console.print(f"[green]✓ Vector cache updated[/green] [dim]({vault.pkm_dir / 'vector.db'})[/dim]")
    console.print(f"[green]✓ Semantic index built:[/green] {count} note(s) indexed [dim]({vault.pkm_dir / 'index.json'})[/dim]")


@click.command("search")
@click.argument("query")
@click.option(
    "--top", "-n", default=10, show_default=True, help="Number of results to return"
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format",
)
@click.option(
    "--type",
    "memory_type",
    type=click.Choice(["episodic", "semantic", "procedural"]),
    default=None,
    help="Filter by memory type",
)
@click.option(
    "--min-importance",
    type=click.FloatRange(1, 10),
    default=1.0,
    help="Minimum importance score",
)
@click.option(
    "--recency-weight",
    type=click.FloatRange(0, 1),
    default=0.0,
    help="Weight for recency+importance scoring (0=pure semantic)",
)
@click.option("--session", "session_id", default=None, help="Filter by session ID")
@click.option("--depth", type=int, default=1, help="Graph traversal depth")
@click.pass_context
def search_cmd(
    ctx: click.Context,
    query: str,
    top: int,
    output_format: str,
    memory_type: str | None,
    min_importance: float,
    recency_weight: float,
    session_id: str | None,
    depth: int,
) -> None:
    """Search vault notes semantically.

    Default output is JSON (machine-readable). Use --format table for human display.

    Memory filters:
      pkm search "error" --type procedural --min-importance 5
      pkm search "session work" --session abc123
      pkm search "recent" --recency-weight 0.4
    """
    vault = ctx.obj["vault"]

    stale_warning: str | None = None
    if is_index_stale(vault):
        stale_warning = "Index may be out of date. Run 'pkm index' to rebuild."

    # Try daemon first (model already loaded in memory → fast path)
    results = search_via_daemon(
        query,
        vault,
        top_n=top,
        min_importance=min_importance,
        memory_type_filter=memory_type,
        recency_weight=recency_weight,
    )

    if results is None:
        # Daemon unavailable — fall back to in-process search
        if output_format == "json":
            logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
            logging.getLogger("transformers").setLevel(logging.ERROR)
            logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        elif stale_warning:
            console.print(f"[yellow]Warning:[/yellow] {stale_warning}")
            stale_warning = None

        def _run_search():
            vector_index = load_index(vault)
            return search_fn(
                query,
                vector_index,
                top_n=top,
                memory_type_filter=memory_type,
                min_importance=min_importance,
                recency_weight=recency_weight,
            )

        if output_format == "json":
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                results = _run_search()
        else:
            results = _run_search()

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

    # Append graph context
    if output_format == "json":
        try:
            from pkm.search_engine import get_graph_context_via_daemon

            for r in results:
                graph_context = get_graph_context_via_daemon(r.note_id, vault, depth)
                if graph_context:
                    r.graph_context = graph_context
        except Exception:
            pass

    if not results and output_format != "json":
        console.print("[yellow]No results found.[/yellow]")
        return

    format_search_results(
        query=query,
        results=results,
        output_format=output_format,
        console=console,
        vault=vault,
        stale_warning=stale_warning,
    )
