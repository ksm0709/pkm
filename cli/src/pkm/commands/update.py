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
        # Installed without a local git repo (e.g. via curl | bash).
        # uv tool upgrade would try to re-fetch from the original (now-deleted) tmp
        # path, so we re-download the latest tarball from GitHub and reinstall.
        import sys
        import tempfile
        import tarfile
        import urllib.request

        GITHUB_REPO = "ksm0709/pkm"
        tarball_url = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/main.tar.gz"
        console.print(f"[cyan]Downloading latest from GitHub...[/cyan]")
        with tempfile.TemporaryDirectory() as tmp:
            tarball_path = Path(tmp) / "pkm.tar.gz"
            try:
                urllib.request.urlretrieve(tarball_url, tarball_path)
            except Exception as e:
                raise click.ClickException(f"Download failed: {e}")

            with tarfile.open(tarball_path, "r:gz") as tf:
                tf.extractall(tmp)

            # The tarball extracts to pkm-main/; cli/ is the package root.
            extracted_dirs = [p for p in Path(tmp).iterdir() if p.is_dir() and p.name != "__MACOSX"]
            if not extracted_dirs:
                raise click.ClickException("Unexpected tarball structure.")
            repo_root = extracted_dirs[0]
            cli_dir = repo_root / "cli"

            search_installed = subprocess.run(
                [sys.executable, "-c", "import sentence_transformers"],
                capture_output=True,
            ).returncode == 0
            install_target = str(cli_dir) + ("[search]" if search_installed else "")
            console.print("[cyan]Reinstalling...[/cyan]")
            result = subprocess.run(
                ["uv", "tool", "install", install_target, "--reinstall-package", "pkm"],
            )
            if result.returncode != 0:
                raise click.ClickException("uv tool install failed.")

    console.print("[green]✓ pkm updated.[/green]")
    result = subprocess.run(["pkm", "--version"], capture_output=True, text=True)
    if result.returncode == 0:
        console.print(result.stdout.strip())
