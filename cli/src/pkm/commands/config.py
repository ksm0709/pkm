"""Configuration management commands."""

from __future__ import annotations

import json

import click
from rich.console import Console
from rich.table import Table

from pkm.config import load_config, save_config, discover_vaults

console = Console()

CONFIG_SCHEMA = {
    "default-vault": {
        "internal_key": "vault",
        "description": "Default vault name used when --vault is not specified",
    },
    "editor": {
        "internal_key": "editor",
        "description": "Editor command used by pkm daily edit (e.g. 'vim', 'code --wait')",
    },
    "auto": {
        "internal_key": "auto",
        "description": "Auto-link and split commands execute changes automatically (true/false)",
    },
    "graph-depth": {
        "internal_key": "graph-depth",
        "description": "Default graph traversal depth for search and show commands",
    },
    "model": {
        "internal_key": "model",
        "description": "LLM model used by pkm ask (default: auto)",
    },
    "reasoning-effort": {
        "internal_key": "reasoning-effort",
        "description": "Reasoning effort for capable models (e.g., low, medium, high)",
    },
    "graph-semantic-candidate-threshold": {
        "internal_key": "graph-semantic-candidate-threshold",
        "description": "Raw cosine floor for semantic graph edge candidates",
    },
    "graph-semantic-score-threshold": {
        "internal_key": "graph-semantic-score-threshold",
        "description": "Final adjusted semantic score floor for graph edges",
    },
    "graph-semantic-mutual-top-k": {
        "internal_key": "graph-semantic-mutual-top-k",
        "description": "Require each endpoint to rank the other within this top-k",
    },
    "graph-semantic-shared-neighbor-k": {
        "internal_key": "graph-semantic-shared-neighbor-k",
        "description": "Neighborhood size used for shared-nearest-neighbor scoring",
    },
    "graph-semantic-local-neighbor-k": {
        "internal_key": "graph-semantic-local-neighbor-k",
        "description": "Neighborhood size used for local density and CSLS scoring",
    },
    "graph-semantic-weight-cosine": {
        "internal_key": "graph-semantic-weight-cosine",
        "description": "Adjusted semantic score weight for raw cosine",
    },
    "graph-semantic-weight-rank": {
        "internal_key": "graph-semantic-weight-rank",
        "description": "Adjusted semantic score weight for reciprocal rank",
    },
    "graph-semantic-weight-csls": {
        "internal_key": "graph-semantic-weight-csls",
        "description": "Adjusted semantic score weight for CSLS-style hubness correction",
    },
    "graph-semantic-weight-shared-neighbor": {
        "internal_key": "graph-semantic-weight-shared-neighbor",
        "description": "Adjusted semantic score weight for shared nearest neighbors",
    },
    "graph-semantic-weight-local-z": {
        "internal_key": "graph-semantic-weight-local-z",
        "description": "Adjusted semantic score weight for local z-score",
    },
    "graph-semantic-min-description-chars": {
        "internal_key": "graph-semantic-min-description-chars",
        "description": "Drop semantic candidates whose auto description is shorter than this",
    },
    "graph-semantic-finance-cross-domain-mode": {
        "internal_key": "graph-semantic-finance-cross-domain-mode",
        "description": "How to handle finance/non-finance semantic candidates: off, penalize, block",
    },
    "graph-semantic-finance-cross-domain-penalty": {
        "internal_key": "graph-semantic-finance-cross-domain-penalty",
        "description": "Score penalty when finance cross-domain mode is penalize",
    },
}

VALID_KEYS = set(CONFIG_SCHEMA.keys())


def _build_docstring() -> str:
    lines = [
        "Manage PKM configuration.",
        "",
        "\b",
        "Available keys:",
    ]
    max_key_len = max(len(k) for k in VALID_KEYS)
    for k, v in sorted(CONFIG_SCHEMA.items()):
        lines.append(f"  {k:<{max_key_len}}   {v['description']}")

    lines.extend(
        [
            "",
            "\b",
            "Examples:",
            "  pkm config set default-vault bear",
            "  pkm config set editor vim",
            "  pkm config get default-vault",
            "  pkm config list",
        ]
    )
    return "\n".join(lines)


@click.group(help=_build_docstring())
def config() -> None:
    pass


@config.command(name="set")
@click.argument("key")
@click.argument("value")
def set_config(key: str, value: str) -> None:
    """Set a configuration value."""
    if key not in VALID_KEYS:
        raise click.ClickException(
            f"Unknown key '{key}'. Valid keys: {', '.join(sorted(VALID_KEYS))}"
        )

    data = load_config()
    defaults = dict(data.get("defaults", {}))
    data = dict(data)

    schema = CONFIG_SCHEMA[key]
    internal_key = schema["internal_key"]

    if key == "default-vault":
        vaults = discover_vaults()
        if value not in vaults:
            console.print(
                f"[yellow]Warning: vault '{value}' not found in discovered vaults.[/yellow]"
            )

    defaults[internal_key] = value
    console.print(f"[green]✓ Set {key} = {value}[/green]")

    data["defaults"] = defaults
    save_config(data)


@config.command(name="get")
@click.argument("key")
def get_config(key: str) -> None:
    """Get a configuration value."""
    if key not in VALID_KEYS:
        raise click.ClickException(
            f"Unknown key '{key}'. Valid keys: {', '.join(sorted(VALID_KEYS))}"
        )

    defaults = load_config().get("defaults", {})
    internal_key = CONFIG_SCHEMA[key]["internal_key"]
    value = defaults.get(internal_key)
    console.print(value if value is not None else "not set")


@config.command(name="list")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format",
)
def list_config(output_format: str) -> None:
    """List all configuration settings."""
    data = load_config()

    defaults = data.get("defaults", {})

    rows = [
        (
            key,
            str(defaults.get(schema["internal_key"], "not set")),
            schema["description"],
        )
        for key, schema in sorted(CONFIG_SCHEMA.items())
    ]

    if output_format == "json":
        print(
            json.dumps(
                {r[0]: r[1] for r in rows if r[1] != "not set"},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Key")
        table.add_column("Value")
        table.add_column("Description")
        for k, v, d in rows:
            table.add_row(k, v, d)

        console.print(table)
