"""pkm update — pull latest or a specific version and reinstall."""

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


def _normalize_tag(version: str) -> str:
    """Ensure version has a 'v' prefix (e.g. '0.3.0' → 'v0.3.0')."""
    return version if version.startswith("v") else f"v{version}"


@click.command("update")
@click.argument("version", default=None, required=False)
def update_cmd(version: str | None) -> None:
    """Update pkm to the latest version, or a specific VERSION tag (e.g. v0.3.0)."""
    cli_dir = _find_cli_dir()

    if cli_dir is not None and (cli_dir.parent / ".git").exists():
        repo_dir = cli_dir.parent

        if version:
            tag = _normalize_tag(version)
            console.print(f"[cyan]Fetching tags from {repo_dir}...[/cyan]")
            result = subprocess.run(["git", "-C", str(repo_dir), "fetch", "--tags"])
            if result.returncode != 0:
                raise click.ClickException("git fetch failed.")

            console.print(f"[cyan]Checking out {tag}...[/cyan]")
            result = subprocess.run(["git", "-C", str(repo_dir), "checkout", tag])
            if result.returncode != 0:
                raise click.ClickException(
                    f"Could not checkout {tag}. Run 'git -C {repo_dir} tag' to see available versions."
                )
        else:
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
        if version:
            raise click.ClickException(
                "Specific version installs require a local git checkout. "
                "Clone the repo: git clone https://github.com/ksm0709/pkm ~/repos/pkm"
            )
        console.print("[cyan]Upgrading via uv tool...[/cyan]")
        result = subprocess.run(["uv", "tool", "upgrade", "pkm"])
        if result.returncode != 0:
            raise click.ClickException("uv tool upgrade failed.")

    console.print("[green]✓ pkm updated.[/green]")
    result = subprocess.run(["pkm", "--version"], capture_output=True, text=True)
    if result.returncode == 0:
        console.print(result.stdout.strip())
