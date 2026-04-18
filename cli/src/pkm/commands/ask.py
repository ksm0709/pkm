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
        try:
            import litellm

            console.print("[bold cyan]Available LiteLLM Providers:[/bold cyan]")
            providers = sorted(list(litellm.models_by_provider.keys()))
            console.print(", ".join(providers))
            console.print(
                "\n[dim]Note: Most providers require specific API keys (e.g. OPENAI_API_KEY, ANTHROPIC_API_KEY).[/dim]"
            )
            console.print(
                "[dim]For a full list of models per provider, visit: https://docs.litellm.ai/docs/providers[/dim]"
            )
            sys.exit(0)
        except ImportError:
            console.print(
                "[red]Error:[/red] litellm is not installed. Please install it (e.g. `uv pip install litellm`) to list models."
            )
            sys.exit(1)

    from pkm.config import load_config

    config_model = load_config().get("defaults", {}).get("model")
    final_model = model or config_model or "gemini/gemini-3.1-flash-preview"

    if not query:
        console.print(f"Current LLM model: [bold green]{final_model}[/bold green]\n")
        click.echo(ctx.get_help())
        sys.exit(1)

    vault = ctx.obj["vault"]
    query_str = " ".join(query)

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
