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
