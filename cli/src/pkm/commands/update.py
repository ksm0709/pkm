"""pkm update — pull latest and reinstall."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click
from rich.console import Console

console = Console()


def _find_cli_dir() -> Path | None:
    """Walk up from this file to find the cli/ root (has pyproject.toml)."""
    d = Path(__file__).parent
    while d != d.parent:
        if (d / "pyproject.toml").exists():
            return d
        d = d.parent
    return None


@click.command("update")
def update_cmd() -> None:
    """Update pkm to the latest version."""
    cli_dir = _find_cli_dir()

    if cli_dir is not None and (cli_dir.parent / ".git").exists():
        repo_dir = cli_dir.parent
        console.print(f"[cyan]Pulling latest from {repo_dir}...[/cyan]")
        result = subprocess.run(["git", "-C", str(repo_dir), "pull"])
        if result.returncode != 0:
            raise click.ClickException("git pull failed.")

        console.print("[cyan]Reinstalling...[/cyan]")
        result = subprocess.run(
            ["uv", "tool", "install", "--editable", str(cli_dir), "--reinstall-package", "pkm"],
        )
        if result.returncode != 0:
            raise click.ClickException("uv tool install failed.")
    else:
        console.print("[cyan]Upgrading via uv tool...[/cyan]")
        result = subprocess.run(["uv", "tool", "upgrade", "pkm"])
        if result.returncode != 0:
            raise click.ClickException("uv tool upgrade failed.")

    console.print("[green]✓ pkm updated.[/green]")
    result = subprocess.run(["pkm", "--version"], capture_output=True, text=True)
    if result.returncode == 0:
        console.print(result.stdout.strip())
