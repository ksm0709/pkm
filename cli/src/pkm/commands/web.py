"""Manage the systemd user unit for the PKM web/daemon service."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys

import click
from rich.console import Console

console = Console()

UNIT_NAME = "pkm-web"
TRYCLOUDFLARE_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)


def _run_systemctl(*args: str) -> int:
    """Run `systemctl --user <args>` and stream output. Return exit code."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", *args],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        click.echo("systemctl not found on this system.", err=True)
        return 127
    if result.stdout:
        click.echo(result.stdout, nl=False)
    if result.returncode != 0 and result.stderr:
        click.echo(result.stderr, nl=False, err=True)
    elif result.stderr:
        click.echo(result.stderr, nl=False, err=True)
    return result.returncode


def _cloudflared_quick_tunnel_args(port: int) -> list[str]:
    return ["tunnel", "--url", f"http://127.0.0.1:{port}"]


def _print_cloudflared_install_help() -> None:
    console.print("[red]cloudflared is not installed.[/red]")
    console.print(
        "Install Cloudflare Tunnel, then run "
        "[bold cyan]pkm web tunnel[/bold cyan] again."
    )
    console.print("The tunnel provides an HTTPS https://*.trycloudflare.com URL.")
    console.print(
        "Linux: https://developers.cloudflare.com/cloudflare-one/connections/"
        "connect-networks/downloads/"
    )


@click.group("web")
def web_group() -> None:
    """Manage the pkm-web systemd user unit."""


@web_group.command("start")
def web_start() -> None:
    """Start the pkm-web user service."""
    code = _run_systemctl("start", UNIT_NAME)
    sys.exit(code)


@web_group.command("stop")
def web_stop() -> None:
    """Stop the pkm-web user service."""
    code = _run_systemctl("stop", UNIT_NAME)
    sys.exit(code)


@web_group.command("restart")
def web_restart() -> None:
    """Restart the pkm-web user service."""
    code = _run_systemctl("restart", UNIT_NAME)
    sys.exit(code)


@web_group.command("status")
def web_status() -> None:
    """Show pkm-web user service status."""
    code = _run_systemctl("status", UNIT_NAME, "--no-pager")
    sys.exit(code)


@web_group.command("enable")
def web_enable() -> None:
    """Enable pkm-web user service to start on login."""
    code = _run_systemctl("enable", UNIT_NAME)
    sys.exit(code)


@web_group.command("tunnel")
@click.option(
    "--port",
    default=7420,
    show_default=True,
    type=int,
    help="Local PKM web daemon port to expose.",
)
def web_tunnel(port: int) -> None:
    """Expose PKM web through a temporary HTTPS Cloudflare tunnel."""
    cloudflared = shutil.which("cloudflared")
    if cloudflared is None:
        _print_cloudflared_install_help()
        raise SystemExit(1)

    args = _cloudflared_quick_tunnel_args(port)
    console.print(
        "Starting HTTPS quick tunnel for "
        f"[bold]http://127.0.0.1:{port}[/bold]."
    )
    console.print("Use the printed https://*.trycloudflare.com URL for PWA install.")
    console.print("[dim]Press Ctrl-C to stop the tunnel.[/dim]")

    proc = subprocess.Popen(
        [cloudflared, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="")
            match = TRYCLOUDFLARE_URL_RE.search(line)
            if match:
                console.print(f"\n[green]PWA install URL:[/green] {match.group(0)}\n")
        raise SystemExit(proc.wait())
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        raise SystemExit(0)
