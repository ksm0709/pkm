"""Graph commands for PKM CLI."""

from __future__ import annotations

import json

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group("graph")
def graph_group() -> None:
    """Graph analysis commands."""


@graph_group.command("surprising")
@click.option(
    "--top",
    "-n",
    "top",
    default=20,
    show_default=True,
    help="Number of results to show.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format. Default JSON is machine-readable; use 'table' for human display.",
)
@click.pass_context
def surprising_cmd(ctx: click.Context, top: int, output_format: str) -> None:
    """Show surprising cross-cluster bridge notes.

    Default output is JSON (machine-readable). Use --format table for human display.
    """
    vault = ctx.obj["vault"]
    from pkm.graph import find_surprising_connections

    results = find_surprising_connections(vault, top_n=top)

    if output_format == "json":
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
        return

    if not results:
        console.print(
            "[yellow]No surprising connections found.[/yellow] "
            "Run [bold cyan]pkm index[/bold cyan] first to build the enriched graph."
        )
        return

    table = Table(title=f"Top {len(results)} Bridge Notes", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Note", style="bold cyan")
    table.add_column("Clusters", style="green")
    table.add_column("Score", justify="right")
    table.add_column("dist_a", justify="right", style="dim")
    table.add_column("dist_b", justify="right", style="dim")

    for i, r in enumerate(results, 1):
        table.add_row(
            str(i),
            r["title"],
            f"{r['cluster_a']}\u2194{r['cluster_b']}",
            f"{r['bridge_score']:.3f}",
            f"{r['dist_a']:.2f}",
            f"{r['dist_b']:.2f}",
        )

    console.print(table)


@graph_group.command("neighbors")
@click.argument("note_id")
@click.option(
    "--semantic",
    is_flag=True,
    default=False,
    help="Include semantic similarity edges (requires pkm index with embeddings).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format. Default JSON is machine-readable; use 'table' for human display.",
)
@click.pass_context
def neighbors_cmd(
    ctx: click.Context, note_id: str, semantic: bool, output_format: str
) -> None:
    """Show all neighbors of a note: outbound links, inbound backlinks, tags, and ghost nodes.

    Default output is JSON (machine-readable). Use --format table for human display.
    Use --semantic to include embedding-based similarity connections.
    """
    import sys
    from pkm.tools.links import _get_note_neighbors_data

    vault = ctx.obj["vault"]
    try:
        result = _get_note_neighbors_data(vault, note_id, semantic)
    except FileNotFoundError:
        console.print(
            "[red]Error:[/red] graph.json not found. "
            "Run [bold cyan]pkm index[/bold cyan] first."
        )
        sys.exit(1)

    if output_format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    outbound, inbound, sem = result["outbound"], result["inbound"], result["semantic"]

    if not outbound and not inbound and not sem:
        console.print(f"[yellow]No connections found for '{note_id}'.[/yellow]")
        return

    table = Table(title=f"Neighbors of {note_id}", show_lines=False)
    table.add_column("Section", style="dim", width=10)
    table.add_column("note_id", style="bold cyan")
    table.add_column("Title")
    table.add_column("Type", style="green")

    for item in outbound:
        table.add_row("outbound", item["note_id"], item["title"], item["type"])
    for item in inbound:
        table.add_row("inbound", item["note_id"], item["title"], item["type"])
    for item in sem:
        conf = f"{item.get('confidence', 0):.2f}"
        table.add_row("semantic", item["note_id"], item["title"], f"semantic ({conf})")

    console.print(table)
