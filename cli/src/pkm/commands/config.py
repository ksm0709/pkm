"""Configuration management commands."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from pkm.config import load_config, save_config, discover_vaults

console = Console()

VALID_KEYS = {"default-vault"}

CONFIG_HELP = {
    "default-vault": "Default vault name used when --vault is not specified",
}


@click.group()
def config() -> None:
    """Manage PKM configuration.

    \b
    Available keys:
      default-vault   Default vault name used when --vault is not specified

    \b
    Examples:
      pkm config set default-vault bear
      pkm config get default-vault
      pkm config list
    """


@config.command(name="set")
@click.argument("key")
@click.argument("value")
def set_config(key: str, value: str) -> None:
    """Set a configuration value."""
    if key not in VALID_KEYS:
        raise click.ClickException(
            f"Unknown key '{key}'. Valid keys: {', '.join(sorted(VALID_KEYS))}"
        )

    if key == "default-vault":
        vaults = discover_vaults()
        if value not in vaults:
            console.print(
                f"[yellow]Warning: vault '{value}' not found in discovered vaults.[/yellow]"
            )

        data = load_config()
        defaults = dict(data.get("defaults", {}))
        defaults["vault"] = value
        data = dict(data)
        data["defaults"] = defaults
        save_config(data)
        console.print(f"[green]✓ Set default-vault = {value}[/green]")


@config.command(name="get")
@click.argument("key")
def get_config(key: str) -> None:
    """Get a configuration value."""
    if key not in VALID_KEYS:
        raise click.ClickException(
            f"Unknown key '{key}'. Valid keys: {', '.join(sorted(VALID_KEYS))}"
        )

    if key == "default-vault":
        value = load_config().get("defaults", {}).get("vault")
        console.print(value if value is not None else "not set")


@config.command(name="list")
def list_config() -> None:
    """List all configuration settings."""
    data = load_config()

    rows: list[tuple[str, str]] = []
    defaults = data.get("defaults", {})
    if "vault" in defaults:
        rows.append(("default-vault", defaults["vault"]))

    if not rows:
        console.print("No configuration set.")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Key")
    table.add_column("Value")
    for k, v in rows:
        table.add_row(k, v)

    console.print(table)
