"""CLI commands for managing PKM daemon workflows."""

from __future__ import annotations

import json
import time
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from pkm.credential_store import agent_credential_env
from pkm.workflows import load_workflows
from pkm.workflows.history import read_workflow_history

_console = Console()


def _hook_label(hook: str | None) -> str:
    return hook.rsplit(":", 1)[-1] if hook else "—"


@click.group(name="workflow")
def workflow_group():
    """Manage PKM daemon workflows."""


@workflow_group.command(name="list")
@click.option("--vault", "-v", default=None, help="Vault path for override resolution")
@click.option(
    "--format",
    "-f",
    "fmt",
    default="json",
    type=click.Choice(["json", "table"]),
    help="Output format",
)
def workflow_list(vault: str | None, fmt: str):
    """List all configured workflows."""
    vault_path = Path(vault) if vault else None
    configs = load_workflows(vault_path=vault_path)

    if fmt == "json":
        click.echo(
            json.dumps(
                [
                    {
                        "id": c.id,
                        "schedule_hour": c.schedule_hour,
                        "jitter_type": c.jitter_type,
                        "marker_file": c.marker_file,
                        "enabled": c.enabled,
                        "model": c.model,
                        "pre_hook": c.pre_hook,
                        "post_hook": c.post_hook,
                    }
                    for c in configs
                ],
                indent=2,
            )
        )
        return

    if not configs:
        _console.print("[yellow]No workflows configured.[/yellow]")
        _console.print("Add workflows to [bold]~/.config/pkm/workflow.json[/bold]")
        return

    table = Table(title="PKM Workflows", show_lines=True)
    table.add_column("ID", style="bold cyan")
    table.add_column("Hour", justify="center")
    table.add_column("Enabled", justify="center")
    table.add_column("Model", style="dim")
    table.add_column("Jitter", style="dim")
    table.add_column("Marker File", style="dim")
    table.add_column("Pre-hook", style="green")
    table.add_column("Post-hook", style="green")

    for c in configs:
        table.add_row(
            c.id,
            str(c.schedule_hour),
            "yes" if c.enabled else "no",
            c.model,
            c.jitter_type,
            c.marker_file,
            _hook_label(c.pre_hook),
            _hook_label(c.post_hook),
        )

    _console.print(table)


def _workflow_vault_path(ctx: click.Context, vault: str | None = None) -> Path:
    if vault:
        return Path(vault)
    try:
        vault_obj = ctx.obj.get("vault") if ctx.obj else None
        if vault_obj:
            return vault_obj.path
    except Exception:
        pass
    return Path(".")


@workflow_group.command(name="run")
@click.argument("workflow_id")
@click.pass_context
def workflow_run(ctx: click.Context, workflow_id: str):
    """Immediately run a workflow by ID via the daemon task queue."""
    vault_path = _workflow_vault_path(ctx)

    configs = load_workflows(vault_path=vault_path)
    config_map = {c.id: c for c in configs}

    if workflow_id not in config_map:
        available = ", ".join(config_map.keys()) or "none"
        _console.print(
            f"[red]Unknown workflow ID:[/red] [bold]{workflow_id}[/bold]\n"
            f"Available: {available}"
        )
        raise SystemExit(1)

    queue_path = Path.home() / ".config" / "pkm" / "task_queue.json"

    try:
        queue: list = (
            json.loads(queue_path.read_text(encoding="utf-8"))
            if queue_path.exists()
            else []
        )
        if not isinstance(queue, list):
            queue = []
    except Exception:
        queue = []

    vault_dir = str(vault_path)
    task = {
        "type": "task",
        "id": f"{workflow_id}_manual_{int(time.time())}",
        "task_type": "workflow",
        "workflow_id": workflow_id,
        "model": config_map[workflow_id].model,
        "workflow_source": "manual",
        "env_keys": agent_credential_env(),
        "env": {"PKM_VAULT_DIR": vault_dir},
    }
    queue.append(task)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps(queue), encoding="utf-8")

    _console.print(
        f"[green]Queued workflow[/green] [bold]{workflow_id}[/bold] → task id: {task['id']}"
    )


@workflow_group.command(name="history")
@click.argument("workflow_id", required=False, default="all")
@click.option("--vault", "-v", default=None, help="Vault path for history lookup")
@click.option("--limit", default=20, show_default=True, help="Maximum rows to show")
@click.option(
    "--format",
    "-f",
    "fmt",
    default="table",
    type=click.Choice(["table", "json"]),
    help="Output format",
)
@click.pass_context
def workflow_history(
    ctx: click.Context,
    workflow_id: str,
    vault: str | None,
    limit: int,
    fmt: str,
):
    """Show recent workflow execution history."""
    vault_path = _workflow_vault_path(ctx, vault)
    selected_workflow = None if workflow_id == "all" else workflow_id
    records = read_workflow_history(
        vault_path,
        workflow_id=selected_workflow,
        limit=limit,
    )

    if fmt == "json":
        click.echo(json.dumps(records, ensure_ascii=False, indent=2))
        return

    if not records:
        _console.print("[yellow]No workflow history found.[/yellow]")
        return

    table = Table(title="PKM Workflow History", show_lines=True)
    table.add_column("Time", style="dim")
    table.add_column("Workflow", style="bold cyan")
    table.add_column("Host", style="dim")
    table.add_column("Status")
    table.add_column("Summary / Error")

    for record in records:
        status = str(record.get("status", ""))
        status_text = (
            f"[green]{status}[/green]"
            if status == "success"
            else f"[red]{status}[/red]"
        )
        details = str(record.get("result_summary") or "")
        if record.get("error"):
            error = f"[red]{record['error']}[/red]"
            details = f"{details}\n{error}" if details else error
        table.add_row(
            str(record.get("time", "")),
            str(record.get("workflow_id", "")),
            str(record.get("hostname", "")),
            status_text,
            details,
        )

    _console.print(table)
