"""Daemon management commands for the background ML search server."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys

import click
from rich.console import Console

from pkm.daemon import SOCKET_PATH, LOG_PATH

console = Console()


def _is_daemon_alive() -> bool:
    """Return True if the daemon socket is reachable."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(str(SOCKET_PATH))
        return True
    except (FileNotFoundError, ConnectionRefusedError, socket.timeout, OSError):
        return False


def _get_daemon_pid() -> int | None:
    """Return the PID of the running daemon process, or None."""
    try:
        import psutil

        for proc in psutil.process_iter(["pid", "cmdline"]):
            cmdline = proc.info.get("cmdline") or []
            if "pkm.daemon" in " ".join(cmdline):
                return proc.info["pid"]
    except ImportError:
        pass
    # Fallback: grep /proc
    try:
        result = subprocess.run(
            ["pgrep", "-f", "pkm.daemon"],
            capture_output=True,
            text=True,
        )
        pids = result.stdout.strip().split()
        if pids:
            return int(pids[0])
    except Exception:
        pass
    return None


@click.group("daemon")
def daemon_group() -> None:
    """Manage the background ML daemon for fast semantic search."""


@daemon_group.command("status")
def daemon_status() -> None:
    """Show whether the daemon is running."""
    pid = _get_daemon_pid()
    alive = _is_daemon_alive()

    if alive:
        pid_str = f"PID {pid}" if pid else "PID unknown"
        console.print(f"[green]running[/green]  ({pid_str})")
        console.print(f"Socket: [dim]{SOCKET_PATH}[/dim]")
    elif pid:
        console.print(
            f"[yellow]stale[/yellow]  (PID {pid} exists but socket unresponsive)"
        )
    else:
        console.print("[red]stopped[/red]")
        console.print("Run [bold cyan]pkm daemon start[/bold cyan] to launch it.")


@daemon_group.command("start")
def daemon_start() -> None:
    """Start the daemon in the background."""
    if _is_daemon_alive():
        console.print("[yellow]Daemon is already running.[/yellow]")
        return

    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "pkm.daemon"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        console.print(f"[green]Daemon started[/green] (PID {proc.pid})")
        console.print(f"Logs: [dim]{LOG_PATH}[/dim]")
    except Exception as exc:
        console.print(f"[red]Failed to start daemon:[/red] {exc}")
        raise SystemExit(1)


@daemon_group.command("stop")
def daemon_stop() -> None:
    """Stop the running daemon."""
    pid = _get_daemon_pid()
    if not pid:
        console.print("[yellow]Daemon is not running.[/yellow]")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        console.print(f"[green]Daemon stopped[/green] (PID {pid})")
    except ProcessLookupError:
        console.print("[yellow]Process not found (already stopped?).[/yellow]")
    except PermissionError:
        console.print(f"[red]Permission denied to stop PID {pid}.[/red]")
        raise SystemExit(1)


@daemon_group.command("restart")
@click.pass_context
def daemon_restart(ctx: click.Context) -> None:
    """Restart the daemon."""
    ctx.invoke(daemon_stop)
    ctx.invoke(daemon_start)


@daemon_group.command("logs")
@click.option(
    "--lines", "-n", default=50, show_default=True, help="Number of lines to show"
)
@click.option("--follow", "-f", is_flag=True, help="Follow log output (like tail -f)")
def daemon_logs(lines: int, follow: bool) -> None:
    """Show daemon log output."""
    if not LOG_PATH.exists():
        console.print(f"[yellow]No log file found at {LOG_PATH}[/yellow]")
        return

    if follow:
        os.execvp("tail", ["tail", f"-n{lines}", "-f", str(LOG_PATH)])
    else:
        text = LOG_PATH.read_text(encoding="utf-8")
        tail_lines = text.splitlines()[-lines:]
        console.print("\n".join(tail_lines))
