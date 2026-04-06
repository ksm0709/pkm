"""pkm update — pull latest or a specific version and reinstall."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console

from pkm._install_source import cli_source, find_local_cli_dir
from pkm.commands.setup import install_skill_files
from pkm.version_check import get_recent_versions

console = Console()


def _normalize_tag(version: str) -> str:
    """Ensure version has a 'v' prefix (e.g. '0.3.0' → 'v0.3.0')."""
    return version if version.startswith("v") else f"v{version}"


def _search_installed() -> bool:
    return subprocess.run(
        [sys.executable, "-c", "import sentence_transformers"],
        capture_output=True,
    ).returncode == 0


@click.command("update")
@click.argument("version", default=None, required=False)
def update_cmd(version: str | None) -> None:
    """Update pkm to the latest version, or a specific VERSION tag (e.g. v0.3.0)."""
    cli_dir = find_local_cli_dir()
    in_git_repo = cli_dir is not None and (cli_dir.parent / ".git").exists()

    if in_git_repo:
        repo_dir = cli_dir.parent  # type: ignore[union-attr]

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
        install_target = str(cli_dir) + ("[search]" if _search_installed() else "")
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
        # Installed without a local git repo (e.g. via curl | bash).
        # Re-download the latest tarball from GitHub and reinstall.
        console.print("[cyan]Downloading latest from GitHub...[/cyan]")
        try:
            with cli_source() as (dl_cli_dir, is_local):
                install_target = str(dl_cli_dir) + ("[search]" if _search_installed() else "")
                console.print("[cyan]Reinstalling...[/cyan]")
                result = subprocess.run(
                    ["uv", "tool", "install", install_target, "--reinstall-package", "pkm"],
                )
                if result.returncode != 0:
                    raise click.ClickException("uv tool install failed.")
        except RuntimeError as e:
            raise click.ClickException(str(e))

    console.print("[green]✓ pkm updated.[/green]")

    # Sync skill and command files — removes stale commands from old versions
    install_skill_files()

    result = subprocess.run(["pkm", "--version"], capture_output=True, text=True)
    if result.returncode == 0:
        console.print(result.stdout.strip())
