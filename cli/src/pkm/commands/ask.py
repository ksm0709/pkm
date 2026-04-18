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
@click.argument("query", nargs=-1, required=False)
@click.option(
    "--timeout", type=int, default=120, help="Timeout in seconds to wait for the result"
)
@click.option("--model", type=str, help="LLM model to use (overrides config)")
@click.option(
    "--list-models", is_flag=True, help="List available model providers via litellm"
)
@click.pass_context
def ask_cmd(
    ctx: click.Context,
    query: tuple[str, ...],
    timeout: int,
    model: str | None,
    list_models: bool,
) -> None:
    """Ask a natural language question about your vault."""
    if list_models:
        from pkm.models import get_available_models
        from rich.table import Table

        try:
            import litellm

            console.print("[bold cyan]PKM Recommended LLM Models:[/bold cyan]")

            table = Table(show_header=True, header_style="bold")
            table.add_column("Model ID")
            table.add_column("Provider")
            table.add_column("Context")
            table.add_column("Input/1M")
            table.add_column("Output/1M")
            table.add_column("API Key Ready?")

            for m in get_available_models():
                val = litellm.validate_environment(m.id)
                has_keys = val.get("keys_in_environment", True)
                status = (
                    "[green]Yes[/green]"
                    if has_keys
                    else f"[red]No ({', '.join(val.get('missing_keys', []))})[/red]"
                )

                table.add_row(
                    m.id,
                    m.provider,
                    m.context_window,
                    m.input_cost_1m,
                    m.output_cost_1m,
                    status,
                )

            console.print(table)
            console.print(
                "\n[dim]When model='auto', PKM will automatically use the best available model from this list.[/dim]"
            )
            sys.exit(0)
        except ImportError:
            console.print(
                "[red]Error:[/red] litellm is not installed. Please install it (e.g. `uv pip install litellm`) to list models."
            )
            sys.exit(1)

    from pkm.config import load_config

    config_model = load_config().get("defaults", {}).get("model")
    final_model = model or config_model or "auto"

    if not query:
        console.print(f"Current LLM model: [bold green]{final_model}[/bold green]\n")
        click.echo(ctx.get_help())
        sys.exit(1)

    vault = ctx.obj["vault"]
    query_str = " ".join(query)

    if final_model != "auto":
        try:
            import litellm

            validation = litellm.validate_environment(final_model)
            if not validation.get("keys_in_environment", True):
                missing = validation.get("missing_keys", [])
                if missing:
                    console.print(
                        f"[red]Error:[/red] API keys for model '{final_model}' are missing from your environment: {', '.join(missing)}"
                    )
                    console.print(
                        f'[yellow]Hint: Export them and restart the daemon (e.g. `export {missing[0]}="..." && pkm daemon restart`)[/yellow]'
                    )
                    sys.exit(1)
        except Exception:
            pass

    sock_path = Path.home() / ".config" / "pkm" / "daemon.sock"

    if not sock_path.exists():
        console.print(
            "[red]Error:[/red] Daemon is not running. Start it with 'pkm daemon start'."
        )
        sys.exit(1)

    with console.status(f"[cyan]Asking daemon using model '{final_model}'...[/cyan]"):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect(str(sock_path))

                req = {
                    "action": "ask",
                    "query": query_str,
                    "vault_name": vault.name,
                    "model": final_model,
                }
                sock.sendall(json.dumps(req).encode("utf-8") + b"\n")

                f = sock.makefile("r", encoding="utf-8")
                resp_line = f.readline()

                if not resp_line:
                    console.print("[red]Error:[/red] No response from daemon.")
                    sys.exit(1)

                data = json.loads(resp_line)

                if data.get("type") == "error" or "error" in data:
                    error_msg = data.get("message") or data.get("error", "Unknown error")
                    if error_msg == "BudgetExhausted" or "BudgetExhausted" in error_msg:
                        console.print(
                            "[red]Error:[/red] Token budget exhausted. Please try again later."
                        )
                    else:
                        console.print(f"[red]Error:[/red] {error_msg}")
                    sys.exit(1)

                if "data" in data and "response" in data["data"]:
                    console.print(data["data"]["response"])
                elif "response" in data:
                    console.print(data["response"])
                else:
                    console.print(
                        f"[red]Error:[/red] Invalid response format from daemon: {data}"
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
