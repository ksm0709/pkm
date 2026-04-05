"""pkm update — pull latest or a specific version and reinstall."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click
from rich.console import Console

from pkm.version_check import get_recent_versions

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
            result = subprocess.run(
                ["git", "-C", str(repo_dir), "checkout", tag],
                capture_output=True,
            )
            if result.returncode != 0:
                console.print(f"[red]✗ Version {tag} not found.[/red]")
                # Try GitHub releases first, fallback to local git tags
                versions = get_recent_versions(5)
                if not versions:
                    local = subprocess.run(
                        ["git", "-C", str(repo_dir), "tag", "--sort=-version:refname"],
                        capture_output=True, text=True,
                    )
                    versions = [t for t in local.stdout.splitlines() if t.startswith("v")][:5]
                if versions:
                    console.print("[yellow]Available versions:[/yellow]")
                    for v in versions:
                        console.print(f"  {v}")
                else:
                    console.print("[yellow]No tagged releases found yet.[/yellow]")
                raise click.ClickException(f"Could not checkout {tag}.")
        else:
            console.print(f"[cyan]Pulling latest from {repo_dir}...[/cyan]")
            result = subprocess.run(["git", "-C", str(repo_dir), "pull"])
            if result.returncode != 0:
                raise click.ClickException("git pull failed.")

        console.print("[cyan]Reinstalling...[/cyan]")
        import sys
        search_installed = subprocess.run(
            [sys.executable, "-c", "import sentence_transformers"],
            capture_output=True,
        ).returncode == 0
        install_target = str(cli_dir) + ("[search]" if search_installed else "")
        result = subprocess.run(
            ["uv", "tool", "install", "--editable", install_target, "--reinstall-package", "pkm"],
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
