"""Manage the systemd user unit for the PKM web/daemon service."""

from __future__ import annotations

import subprocess
import sys

import click
from rich.console import Console

console = Console()

UNIT_NAME = "pkm-web"


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
