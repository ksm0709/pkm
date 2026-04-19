"""Natural language reporting command for PKM CLI."""

from __future__ import annotations

import json
import os
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
    graph_depth = load_config().get("defaults", {}).get("graph-depth", 0)

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


    env_keys = {k: v for k, v in os.environ.items() if k.endswith("_API_KEY")}

    sock_path = Path.home() / ".config" / "pkm" / "daemon.sock"

    console.print(f"[dim]Asking daemon using model '{final_model}'...[/dim]")

    import time
    import subprocess

    sock = None
    for attempt in range(50):
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(str(sock_path))
            break
        except (FileNotFoundError, ConnectionRefusedError):
            if sock:
                sock.close()
                sock = None
            if attempt == 0:
                daemon_dir = Path.home() / ".config" / "pkm"
                daemon_dir.mkdir(parents=True, exist_ok=True)
                try:
                    subprocess.Popen(
                        [sys.executable, "-m", "pkm.daemon"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                except Exception as e:
                    console.print(f"[red]Failed to start daemon: {e}[/red]")
                    sys.exit(1)
            time.sleep(0.1)

    if not sock:
        console.print("[red]Error:[/red] Daemon failed to start or connection refused.")
        sys.exit(1)

    try:
        with sock:
            req = {
                "action": "ask",
                "query": query_str,
                "vault_name": vault.name,
                "model": final_model,
                "env_keys": env_keys,
                "graph_depth": graph_depth,
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
        console.print(f"[red]Error:[/red] Request timed out after {timeout} seconds.")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] An unexpected error occurred: {e}")
        sys.exit(1)
