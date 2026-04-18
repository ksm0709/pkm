"""Natural language reporting command for PKM CLI."""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.command("ask")
@click.argument("query", nargs=-1, required=True)
@click.option(
    "--timeout", type=int, default=120, help="Timeout in seconds to wait for the result"
)
@click.pass_context
def ask_cmd(ctx: click.Context, query: tuple[str, ...], timeout: int) -> None:
    """Ask a natural language question about your vault."""
    vault = ctx.obj["vault"]
    query_str = " ".join(query)

    sock_path = Path.home() / ".config" / "pkm" / "daemon.sock"

    if not sock_path.exists():
        console.print(
            "[red]Error:[/red] Daemon is not running. Start it with 'pkm daemon start'."
        )
        sys.exit(1)

    with console.status("[cyan]Asking daemon...[/cyan]"):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect(str(sock_path))

                req = {
                    "action": "ask",
                    "query": query_str,
                    "vault_name": vault.name,
                }
                sock.sendall(json.dumps(req).encode("utf-8") + b"\n")

                f = sock.makefile("r", encoding="utf-8")
                resp_line = f.readline()

                if not resp_line:
                    console.print("[red]Error:[/red] No response from daemon.")
                    sys.exit(1)

                data = json.loads(resp_line)

                if "error" in data:
                    error_msg = data["error"]
                    if error_msg == "BudgetExhausted":
                        console.print(
                            "[red]Error:[/red] Token budget exhausted. Please try again later."
                        )
                    else:
                        console.print(f"[red]Error:[/red] {error_msg}")
                    sys.exit(1)

                if "result" in data:
                    console.print(data["result"])
                else:
                    console.print(
                        "[red]Error:[/red] Invalid response format from daemon."
                    )
                    sys.exit(1)

        except socket.timeout:
            console.print(
                f"[red]Error:[/red] Request timed out after {timeout} seconds."
            )
            sys.exit(1)
        except ConnectionRefusedError:
            console.print(
                "[red]Error:[/red] Connection refused. Is the daemon running?"
            )
            sys.exit(1)
        except Exception as e:
            console.print(f"[red]Error:[/red] An unexpected error occurred: {e}")
            sys.exit(1)
