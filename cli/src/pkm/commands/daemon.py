"""Daemon management commands for the background ML search server."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time

import click
from rich.console import Console

from pkm.daemon import (
    EXIT_REASON_IDLE,
    EXIT_STATE_PATH,
    LOCK_PATH,
    LOG_PATH,
    SOCKET_PATH,
    daemon_argv_matches,
    daemon_lock_held,
    read_process_cmdline,
)

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
    try:
        pid = int(LOCK_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if pid <= 0 or not daemon_lock_held(LOCK_PATH):
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        pass
    except OSError:
        return None
    cmdline = read_process_cmdline(pid)
    if cmdline is not None and not daemon_argv_matches(cmdline):
        return None
    return pid


def daemon_status_code() -> str:
    if _is_daemon_alive():
        return "running"
    if _get_daemon_pid():
        return "stale"
    try:
        reason = EXIT_STATE_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        reason = ""
    return "idle_exit" if reason == EXIT_REASON_IDLE else "stopped"


@click.group("daemon")
def daemon_group() -> None:
    """Manage the background ML daemon for fast semantic search."""


@daemon_group.command("status")
def daemon_status() -> None:
    """Show whether the daemon is running."""
    code = daemon_status_code()
    pid = _get_daemon_pid()

    if code == "running":
        pid_str = f"PID {pid}" if pid else "PID unknown"
        console.print(f"[green]running[/green]  ({pid_str})")
        console.print(f"Socket: [dim]{SOCKET_PATH}[/dim]")
    elif code == "stale":
        console.print(
            f"[yellow]stale[/yellow]  (PID {pid} exists but socket unresponsive)"
        )
    else:
        label = "stopped (idle exit)" if code == "idle_exit" else "stopped"
        console.print(f"[red]{label}[/red]")
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
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        console.print(f"[green]Daemon started[/green] (PID {proc.pid})")
        console.print(f"Logs: [dim]{LOG_PATH}[/dim]")
    except Exception as exc:
        console.print(f"[red]Failed to start daemon:[/red] {exc}")
        raise SystemExit(1)


@daemon_group.command("run")
def daemon_run() -> None:
    """Run the daemon in the foreground for process managers."""
    from pkm.daemon import main as daemon_main

    daemon_main()


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
    for _ in range(30):  # wait up to 3s for socket to close
        if not _is_daemon_alive():
            break
        time.sleep(0.1)
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
