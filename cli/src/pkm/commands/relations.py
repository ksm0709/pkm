"""Relation vocabulary and audit commands for PKM CLI."""

from __future__ import annotations

import json

import click
from rich.console import Console
from rich.table import Table

from pkm.relations import (
    is_valid_relation_name,
    load_or_scan_relation_payloads,
    promote_relation,
)

console = Console()


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
def relations(ctx: click.Context, output_format: str) -> None:
    """Show relation vocabulary and observed usage."""
    if ctx.invoked_subcommand is not None:
        return

    vault = ctx.obj["vault"]
    vocabulary, _audit, cache_status = load_or_scan_relation_payloads(vault)
    payload = {**vocabulary, "cache_status": cache_status}
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(title="Relations", show_header=True, header_style="bold cyan")
    table.add_column("Relation", style="green")
    table.add_column("Status")
    table.add_column("Count", justify="right")
    for relation_type, usage in vocabulary.get("observed", {}).items():
        table.add_row(
            relation_type, usage.get("status", "observed"), str(usage.get("count", 0))
        )
    console.print(table)


@relations.command()
@click.argument("relation_type")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format",
)
@click.pass_context
def show(ctx: click.Context, relation_type: str, output_format: str) -> None:
    """Show one relation definition and usage."""
    vault = ctx.obj["vault"]
    vocabulary, _audit, cache_status = load_or_scan_relation_payloads(vault)
    relation = _find_relation(vocabulary, relation_type)
    usage = vocabulary.get("observed", {}).get(
        relation_type,
        {
            "type": relation_type,
            "count": 0,
            "status": "unknown",
            "examples": [],
            "common_sources": [],
            "common_targets": [],
        },
    )
    payload = {"relation": relation, "usage": usage, "cache_status": cache_status}
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    console.print_json(json.dumps(payload, ensure_ascii=False))


@relations.command()
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format",
)
@click.pass_context
def observed(ctx: click.Context, output_format: str) -> None:
    """List observed relation types not present in vocabulary."""
    vault = ctx.obj["vault"]
    vocabulary, _audit, cache_status = load_or_scan_relation_payloads(vault)
    items = [
        usage
        for usage in vocabulary.get("observed", {}).values()
        if usage.get("status") == "observed"
    ]
    payload = {"relations": items, "count": len(items), "cache_status": cache_status}
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(title="Observed Relations", show_header=True, header_style="bold cyan")
    table.add_column("Relation", style="green")
    table.add_column("Count", justify="right")
    for item in items:
        table.add_row(item["type"], str(item["count"]))
    console.print(table)


@relations.command()
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format",
)
@click.pass_context
def audit(ctx: click.Context, output_format: str) -> None:
    """Show advisory relation quality findings."""
    vault = ctx.obj["vault"]
    _vocabulary, audit_payload, cache_status = load_or_scan_relation_payloads(vault)
    payload = {**audit_payload, "cache_status": cache_status}
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(title="Relation Audit", show_header=True, header_style="bold cyan")
    table.add_column("Category", style="green")
    table.add_column("Count", justify="right")
    for key, value in payload.items():
        if isinstance(value, list):
            table.add_row(key, str(len(value)))
    console.print(table)


@relations.command()
@click.argument("relation_type")
@click.pass_context
def promote(ctx: click.Context, relation_type: str) -> None:
    """Promote an observed relation into the vault vocabulary note."""
    if not is_valid_relation_name(relation_type):
        raise click.BadParameter(f"Invalid relation name: {relation_type!r}")
    vault = ctx.obj["vault"]
    path = promote_relation(vault, relation_type)
    print(
        json.dumps(
            {"relation": relation_type, "path": str(path), "promoted": True},
            ensure_ascii=False,
            indent=2,
        )
    )


def _find_relation(vocabulary: dict, relation_type: str) -> dict:
    for section in ("built_in", "vault"):
        if relation_type in vocabulary.get(section, {}):
            return vocabulary[section][relation_type]
    usage = vocabulary.get("observed", {}).get(relation_type)
    if usage:
        return {
            "type": relation_type,
            "description": "",
            "status": usage.get("status", "observed"),
            "aliases": [],
            "inverse": None,
            "examples": [],
        }
    return {
        "type": relation_type,
        "description": "",
        "status": "unknown",
        "aliases": [],
        "inverse": None,
        "examples": [],
    }
