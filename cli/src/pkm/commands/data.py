"""Data file commands for PKM CLI."""

from __future__ import annotations

import shutil
import urllib.error
import urllib.request
from pathlib import Path

import click
from rich.console import Console

console = Console()


def _is_url(source: str) -> bool:
    """Check if source looks like a URL."""
    return source.startswith("http://") or source.startswith("https://")


@click.group(invoke_without_command=True)
@click.pass_context
def data(ctx: click.Context) -> None:
    """Manage data files in the vault."""
    if ctx.invoked_subcommand is None:
        vault = ctx.obj["vault"]
        data_dir = vault.data_dir
        if not data_dir.is_dir():
            click.echo("No data directory yet.")
            return
        files = sorted(data_dir.iterdir())
        if not files:
            click.echo("No data files.")
            return
        for f in files:
            if f.is_file():
                size = f.stat().st_size
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                console.print(f"  {f.name}  [dim]({size_str})[/dim]")


@data.command()
@click.argument("fname")
@click.argument("source")
@click.option("--force", "-f", is_flag=True, help="Overwrite if file already exists")
@click.pass_context
def add(ctx: click.Context, fname: str, source: str, force: bool) -> None:
    """Add a data file to the vault.

    FNAME is the destination filename in the vault's data/ directory.
    SOURCE is a local file path or a URL (http/https).

    Examples:
      pkm data add report.pdf ./downloads/report.pdf
      pkm data add paper.pdf https://example.com/paper.pdf
    """
    vault = ctx.obj["vault"]
    data_dir = vault.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    dest = data_dir / fname

    if dest.exists() and not force:
        raise click.ClickException(
            f"File already exists: {dest.name}. Use --force to overwrite."
        )

    if _is_url(source):
        try:
            urllib.request.urlretrieve(source, str(dest))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            if dest.exists():
                dest.unlink()
            raise click.ClickException(f"Download failed: {exc}") from exc
    else:
        src = Path(source).expanduser().resolve()
        if not src.exists():
            raise click.ClickException(f"Source file not found: {source}")
        if not src.is_file():
            raise click.ClickException(f"Source is not a file: {source}")
        shutil.copy2(str(src), str(dest))

    console.print(f"[green]Added[/green] {dest.name} → {data_dir}")


@data.command()
@click.argument("fname")
@click.pass_context
def rm(ctx: click.Context, fname: str) -> None:
    """Remove a data file from the vault.

    FNAME is the filename in the vault's data/ directory.

    Example:
      pkm data rm report.pdf
    """
    vault = ctx.obj["vault"]
    target = vault.data_dir / fname

    if not target.exists():
        raise click.ClickException(f"File not found: {fname}")
    if not target.is_file():
        raise click.ClickException(f"Not a file: {fname}")

    target.unlink()
    console.print(f"[red]Removed[/red] {fname}")
