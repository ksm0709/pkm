"""Natural language reporting command for PKM CLI."""

from __future__ import annotations

import json
import os
import shutil
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import click
from rich.console import Console

from pkm.credential_store import agent_credential_env

console = Console()

_PKM_TOOLS = {
    "read_daily_log",
    "add_daily_log",
    "read_note",
    "search_notes",
    "semantic_search",
    "add_note",
    "patch_note",
    "update_note",
    "rename_note",
    "get_graph_context",
    "vault_stats",
    "list_stale_notes",
    "list_orphans",
    "list_malformed_notes",
    "find_backlinks_for_note",
    "list_tags",
    "tag_search",
    "list_consolidation_candidates",
    "mark_consolidated",
    "read_recent_note_activity",
}

_HIDDEN_TOOLS = {"turn_start", "turn_stop"}

_TASK_ICONS = {
    "todo": "○",
    "pending": "○",
    "in_progress": "▶",
    "done": "✓",
    "blocked": "✗",
}

_TASK_COLORS = {
    "todo": "dim",
    "pending": "dim",
    "in_progress": "bold cyan",
    "done": "green",
    "blocked": "red",
}


@contextmanager
def _temporary_env(env_keys: dict[str, str]) -> Iterator[None]:
    previous: dict[str, str | None] = {}
    for key, value in env_keys.items():
        previous[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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
        from pkm.models import get_connected_model_options, validate_model_environment
        from rich.table import Table

        try:
            import litellm

            env_keys = agent_credential_env()
            models = get_connected_model_options(env_keys)
            console.print("[bold cyan]PKM Connected LLM Models:[/bold cyan]")
            if not models:
                console.print(
                    "[yellow]No saved or environment API keys found for supported providers.[/yellow]"
                )
                sys.exit(0)

            table = Table(show_header=True, header_style="bold")
            table.add_column("Model ID")
            table.add_column("Provider")
            table.add_column("Context")
            table.add_column("API Key Ready?")

            for model_id in models:
                cost = litellm.model_cost.get(model_id) or {}
                if not cost and "/" in model_id:
                    cost = litellm.model_cost.get(model_id.split("/", 1)[1]) or {}
                provider = cost.get("litellm_provider") or model_id.split("/", 1)[0]
                context = cost.get("max_input_tokens")
                with _temporary_env(env_keys):
                    val = validate_model_environment(model_id)
                has_keys = val.get("keys_in_environment", True)
                status = (
                    "[green]Yes[/green]"
                    if has_keys
                    else f"[red]No ({', '.join(val.get('missing_keys', []))})[/red]"
                )

                table.add_row(
                    model_id,
                    str(provider),
                    str(context or "unknown"),
                    status,
                )

            console.print(table)
            console.print(
                "\n[dim]When model='auto', PKM still uses the recommended fallback order. Explicit selections can use any model in this connected-provider list.[/dim]"
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
    model_candidates = None
    if model is None and config_model and config_model != "auto":
        try:
            from pkm.models import resolve_model_candidates

            model_candidates = resolve_model_candidates(config_model)
        except Exception:
            model_candidates = [config_model]
    graph_depth = config_data.get("graph-depth", 0)

    final_reasoning_effort = reasoning_effort or config_reasoning_effort

    if not query:
        console.print(f"Current LLM model: [bold green]{final_model}[/bold green]\n")
        click.echo(ctx.get_help())
        sys.exit(1)

    vault = ctx.obj["vault"]
    query_str = " ".join(query)

    env_keys = agent_credential_env()

    if final_model != "auto":
        try:
            import litellm

            with _temporary_env(env_keys):
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

    display_model = final_model
    if final_model == "auto":
        try:
            from pkm.models import resolve_auto_models

            resolved = resolve_auto_models()
            if resolved:
                display_model = resolved[0]
        except Exception:
            pass
    console.print(f"[dim]Asking daemon using model '{display_model}'...[/dim]")

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
                "model_candidates": model_candidates,
                "reasoning_effort": final_reasoning_effort,
                "env_keys": env_keys,
                "graph_depth": graph_depth,
                "cwd": os.getcwd(),
            }
            sock.sendall(json.dumps(req).encode("utf-8") + b"\n")

            f = sock.makefile("r", encoding="utf-8")

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
                            sys.stdout.write("\r\033[2K")
                            sys.stdout.flush()
                            has_reasoning = False
                        name = chunk.get("name", "unknown")
                        if name in _HIDDEN_TOOLS:
                            continue
                        args_dict = chunk.get("arguments", {})
                        if name == "manage_tasks":
                            tasks_raw = (
                                args_dict.get("tasks", [])
                                if isinstance(args_dict, dict)
                                else []
                            )
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
                            console.print(
                                f"  [bold green]↳ {name}[/bold green][dim]({arg_str})[/dim]"
                            )
                        elif name == "load_skill":
                            skill_id = (
                                args_dict.get("skill_id", arg_str)
                                if isinstance(args_dict, dict)
                                else arg_str
                            )
                            console.print(
                                f"  [bold cyan]⚡ skill: {skill_id}[/bold cyan]"
                            )
                        else:
                            console.print(f"  [dim]· {name}({arg_str})[/dim]")
                    elif c_type == "reasoning":
                        has_reasoning = True
                        reasoning_text = chunk.get("content", "")
                        if reasoning_text:
                            reasoning_buffer += reasoning_text
                            lines = [
                                line.strip()
                                for line in reasoning_buffer.split("\n")
                                if line.strip()
                            ]
                            display_text = " / ".join(lines[-2:]) if lines else ""
                            term_width = shutil.get_terminal_size().columns
                            max_text = max(20, term_width - len("[thinking] ") - 1)
                            if len(display_text) > max_text:
                                display_text = display_text[-max_text:]
                            sys.stdout.write(
                                f"\r\033[2K\033[38;5;246m[thinking] {display_text}\033[0m"
                            )
                            sys.stdout.flush()
                    continue

                if data.get("type") == "error" or "error" in data:
                    if has_reasoning:
                        sys.stdout.write("\r\033[2K")
                        sys.stdout.flush()
                    error_msg = data.get("message") or data.get(
                        "error", "Unknown error"
                    )
                    console.print(f"[red]Error:[/red] {error_msg}")
                    sys.exit(1)

                if "data" in data and "response" in data["data"]:
                    if has_reasoning:
                        sys.stdout.write("\r\033[2K")
                        sys.stdout.flush()
                    console.print(data["data"]["response"])
                    break
                elif "response" in data:
                    if has_reasoning:
                        sys.stdout.write("\r\033[2K")
                        sys.stdout.flush()
                    console.print(data["response"])
                    break
                else:
                    if data.get("status") == "success":
                        if has_reasoning:
                            console.print("\r\033[K", end="")
                        break
                    if has_reasoning:
                        sys.stdout.write("\r\033[2K")
                        sys.stdout.flush()
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
