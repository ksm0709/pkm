"""Configuration management commands."""

from __future__ import annotations

import json
import os
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from pkm.config import load_config, save_config, discover_vaults

console = Console()

CONFIG_SCHEMA = {
    "default-vault": {
        "internal_key": "vault",
        "description": "Default vault name used when --vault is not specified",
        "default": None,
    },
    "editor": {
        "internal_key": "editor",
        "description": "Editor command used by pkm daily edit (e.g. 'vim', 'code --wait')",
        "default": None,
    },
    "graph-depth": {
        "internal_key": "graph-depth",
        "description": "Default graph traversal depth for search and show commands",
        "default": "0",
    },
    "model": {
        "internal_key": "model",
        "description": "LLM model used by pkm ask (default: auto)",
        "default": "auto",
    },
    "reasoning-effort": {
        "internal_key": "reasoning-effort",
        "description": "Reasoning effort for capable models (e.g., low, medium, high)",
        "default": None,
    },
    "graph-semantic-candidate-threshold": {
        "internal_key": "graph-semantic-candidate-threshold",
        "description": "Raw cosine floor for semantic graph edge candidates",
        "default": "0.7325",
    },
    "graph-semantic-score-threshold": {
        "internal_key": "graph-semantic-score-threshold",
        "description": "Final adjusted semantic score floor for graph edges",
        "default": "0.5952",
    },
    "graph-semantic-mutual-top-k": {
        "internal_key": "graph-semantic-mutual-top-k",
        "description": "Require each endpoint to rank the other within this top-k",
        "default": "40",
    },
    "graph-semantic-shared-neighbor-k": {
        "internal_key": "graph-semantic-shared-neighbor-k",
        "description": "Neighborhood size used for shared-nearest-neighbor scoring",
        "default": "20",
    },
    "graph-semantic-local-neighbor-k": {
        "internal_key": "graph-semantic-local-neighbor-k",
        "description": "Neighborhood size used for local density and CSLS scoring",
        "default": "15",
    },
    "graph-semantic-weight-cosine": {
        "internal_key": "graph-semantic-weight-cosine",
        "description": "Adjusted semantic score weight for raw cosine",
        "default": "0.0",
    },
    "graph-semantic-weight-rank": {
        "internal_key": "graph-semantic-weight-rank",
        "description": "Adjusted semantic score weight for reciprocal rank",
        "default": "0.0652",
    },
    "graph-semantic-weight-csls": {
        "internal_key": "graph-semantic-weight-csls",
        "description": "Adjusted semantic score weight for CSLS-style hubness correction",
        "default": "0.0922",
    },
    "graph-semantic-weight-shared-neighbor": {
        "internal_key": "graph-semantic-weight-shared-neighbor",
        "description": "Adjusted semantic score weight for shared nearest neighbors",
        "default": "0.3244",
    },
    "graph-semantic-weight-local-z": {
        "internal_key": "graph-semantic-weight-local-z",
        "description": "Adjusted semantic score weight for local z-score",
        "default": "0.5182",
    },
    "graph-semantic-min-description-chars": {
        "internal_key": "graph-semantic-min-description-chars",
        "description": "Drop semantic candidates whose auto description is shorter than this",
        "default": "20",
    },
    "graph-semantic-finance-cross-domain-mode": {
        "internal_key": "graph-semantic-finance-cross-domain-mode",
        "description": "How to handle finance/non-finance semantic candidates: off, penalize, block",
        "default": "block",
    },
    "graph-semantic-finance-cross-domain-penalty": {
        "internal_key": "graph-semantic-finance-cross-domain-penalty",
        "description": "Score penalty when finance cross-domain mode is penalize",
        "default": "0.1943",
    },
    "web-port": {
        "section": "web",
        "internal_key": "port",
        "description": "Port used by the pkm web daemon",
        "default": "7420",
    },
    "web-bind": {
        "section": "web",
        "internal_key": "bind",
        "description": "Bind address used by the pkm web daemon",
        "default": "0.0.0.0",
    },
    "web-window-padding": {
        "section": "web",
        "internal_key": "window_padding",
        "description": "Symmetric page window padding in the pkm web app, in px",
        "default": "32",
    },
}

VALID_KEYS = set(CONFIG_SCHEMA.keys())


def config_default_for_key(key: str) -> str | None:
    """Return the effective default for a config key when no value is stored."""
    if key == "editor":
        return os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
    default = CONFIG_SCHEMA[key].get("default")
    return None if default is None else str(default)


def _section_for_key(key: str) -> str:
    return str(CONFIG_SCHEMA[key].get("section", "defaults"))


def _validate_config_value(key: str, value: str) -> str:
    if key == "web-port":
        return _validate_integer_range(key, value, min_value=1, max_value=65535)
    if key == "web-window-padding":
        return _validate_integer_range(key, value, min_value=0, max_value=128)
    return value


def _validate_integer_range(
    key: str, value: str, *, min_value: int, max_value: int
) -> str:
    message = f"{key} must be an integer from {min_value} to {max_value}."
    try:
        parsed = int(value)
    except ValueError:
        raise click.ClickException(message)
    if not min_value <= parsed <= max_value:
        raise click.ClickException(message)
    return str(parsed)


def config_value_for_key(
    key: str, section_values: dict[str, Any], *, unset_label: str = "not set"
) -> tuple[str, str]:
    """Return display value and source: configured, default, or unset."""
    internal_key = CONFIG_SCHEMA[key]["internal_key"]
    if internal_key in section_values:
        return str(section_values[internal_key]), "configured"
    default = config_default_for_key(key)
    if default is not None:
        return default, "default"
    return unset_label, "unset"


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
    section_name = _section_for_key(key)
    section = dict(data.get(section_name, {}))
    data = dict(data)

    schema = CONFIG_SCHEMA[key]
    internal_key = schema["internal_key"]
    value = _validate_config_value(key, value)

    if key == "default-vault":
        vaults = discover_vaults()
        if value not in vaults:
            console.print(
                f"[yellow]Warning: vault '{value}' not found in discovered vaults.[/yellow]"
            )

    section[internal_key] = value
    console.print(f"[green]✓ Set {key} = {value}[/green]")

    data[section_name] = section
    save_config(data)


@config.command(name="get")
@click.argument("key")
def get_config(key: str) -> None:
    """Get a configuration value."""
    if key not in VALID_KEYS:
        raise click.ClickException(
            f"Unknown key '{key}'. Valid keys: {', '.join(sorted(VALID_KEYS))}"
        )

    section = load_config().get(_section_for_key(key), {})
    if not isinstance(section, dict):
        section = {}
    value, _source = config_value_for_key(key, section)
    console.print(value)


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

    rows = [
        (
            key,
            *config_value_for_key(
                key,
                data.get(_section_for_key(key), {})
                if isinstance(data.get(_section_for_key(key), {}), dict)
                else {},
            ),
            CONFIG_SCHEMA[key]["description"],
        )
        for key in sorted(CONFIG_SCHEMA.keys())
    ]

    if output_format == "json":
        print(
            json.dumps(
                {key: value for key, value, source, _desc in rows if source != "unset"},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Key")
        table.add_column("Value")
        table.add_column("Source")
        table.add_column("Description")
        for k, v, source, d in rows:
            table.add_row(k, v, source, d)

        console.print(table)
