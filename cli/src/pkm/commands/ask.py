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
    "--reasoning-effort", type=str, help="Reasoning effort for capable models"
)
@click.option(
    "--list-models", is_flag=True, help="List available model providers via litellm"
)
@click.pass_context
def ask_cmd(
    ctx: click.Context,
    query: tuple[str, ...],
    timeout: int,
    model: str | None,
    reasoning_effort: str | None,
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

    config_data = load_config().get("defaults", {})
    config_model = config_data.get("model")
    config_reasoning_effort = config_data.get("reasoning-effort")
    final_model = model or config_model or "auto"
    graph_depth = config_data.get("graph-depth", 0)

    final_reasoning_effort = reasoning_effort or config_reasoning_effort

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
                "reasoning_effort": final_reasoning_effort,
                "env_keys": env_keys,
                "graph_depth": graph_depth,
                "cwd": os.getcwd(),
            }
            sock.sendall(json.dumps(req).encode("utf-8") + b"\n")

            f = sock.makefile("r", encoding="utf-8")

            _PKM_TOOLS = {
                "read_daily_log", "add_daily_log", "read_note", "search_notes",
                "semantic_search", "add_note", "update_note", "get_graph_context",
            }
            _HIDDEN_TOOLS = {"turn_start", "turn_stop"}
            _TASK_ICONS = {"todo": "○", "pending": "○", "in_progress": "▶", "done": "✓", "blocked": "✗"}
            _TASK_COLORS = {"todo": "dim", "pending": "dim", "in_progress": "bold cyan", "done": "green", "blocked": "red"}

            reasoning_buffer = ""
            has_reasoning = False

            while True:
                resp_line = f.readline()
                if not resp_line:
                    console.print(
                        "[red]Error:[/red] No response from daemon or connection closed."
                    )
                    sys.exit(1)

                data = json.loads(resp_line)

                if data.get("type") == "stream":
                    chunk = data.get("chunk", {})
                    c_type = chunk.get("type")
                    if c_type in ("tool_start", "tool_stop"):
                        pass
                    elif c_type == "tool_detail":
                        if has_reasoning:
                            console.print("\r\033[K", end="")
                            has_reasoning = False
                        name = chunk.get("name", "unknown")
                        if name in _HIDDEN_TOOLS:
                            continue
                        args_dict = chunk.get("arguments", {})
                        if name == "manage_tasks":
                            tasks_raw = args_dict.get("tasks", []) if isinstance(args_dict, dict) else []
                            if isinstance(tasks_raw, str):
                                try:
                                    tasks = json.loads(tasks_raw)
                                except Exception:
                                    tasks = []
                            elif isinstance(tasks_raw, list):
                                tasks = tasks_raw
                            else:
                                tasks = []
                            for t in tasks[:5]:
                                if not isinstance(t, dict):
                                    continue
                                t_name = t.get("title") or t.get("name", "?")
                                t_status = t.get("status", "todo")
                                icon = _TASK_ICONS.get(t_status, "·")
                                color = _TASK_COLORS.get(t_status, "dim")
                                console.print(f"  [{color}]{icon} {t_name}[/{color}]")
                            continue
                        arg_parts = []
                        if isinstance(args_dict, dict):
                            for k, v in args_dict.items():
                                v_str = str(v)
                                if len(v_str) > 50:
                                    v_str = v_str[:47] + "..."
                                arg_parts.append(f"{k}={v_str!r}")
                            arg_str = ", ".join(arg_parts)
                        else:
                            arg_str = str(args_dict)
                            if len(arg_str) > 100:
                                arg_str = arg_str[:97] + "..."
                        if name in _PKM_TOOLS:
                            console.print(f"  [bold green]↳ {name}[/bold green][dim]({arg_str})[/dim]")
                        elif name == "load_skill":
                            skill_id = args_dict.get("skill_id", arg_str) if isinstance(args_dict, dict) else arg_str
                            console.print(f"  [bold cyan]⚡ skill: {skill_id}[/bold cyan]")
                        else:
                            console.print(f"  [dim]· {name}({arg_str})[/dim]")
                    elif c_type == "reasoning":
                        has_reasoning = True
                        reasoning_text = chunk.get("content", "")
                        if reasoning_text:
                            reasoning_buffer += reasoning_text
                            lines = [l.strip() for l in reasoning_buffer.split("\n") if l.strip()]
                            display_text = " / ".join(lines[-2:]) if lines else ""
                            if len(display_text) > 120:
                                display_text = display_text[-120:]
                            console.print(
                                f"\r\033[K[dim italic]\\[thinking] {display_text}[/dim italic]",
                                end="",
                            )
                    continue

                if data.get("type") == "error" or "error" in data:
                    if has_reasoning:
                        console.print("\r\033[K", end="")
                    error_msg = data.get("message") or data.get(
                        "error", "Unknown error"
                    )
                    console.print(f"[red]Error:[/red] {error_msg}")
                    sys.exit(1)

                if "data" in data and "response" in data["data"]:
                    if has_reasoning:
                        console.print("\r\033[K", end="")
                    console.print(data["data"]["response"])
                    break
                elif "response" in data:
                    if has_reasoning:
                        console.print("\r\033[K", end="")
                    console.print(data["response"])
                    break
                else:
                    if data.get("status") == "success":
                        if has_reasoning:
                            console.print("\r\033[K", end="")
                        break
                    if has_reasoning:
                        console.print("\r\033[K", end="")
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
