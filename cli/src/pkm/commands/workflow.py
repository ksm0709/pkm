"""CLI commands for managing PKM daemon workflows."""

from __future__ import annotations

import json
import time
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from pkm.workflows import load_workflows

_console = Console()


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
    table.add_column("Jitter", style="dim")
    table.add_column("Marker File", style="dim")
    table.add_column("Pre-hook", style="green")
    table.add_column("Post-hook", style="green")

    for c in configs:
        table.add_row(
            c.id,
            str(c.schedule_hour),
            c.jitter_type,
            c.marker_file,
            c.pre_hook or "—",
            c.post_hook or "—",
        )

    _console.print(table)


@workflow_group.command(name="run")
@click.argument("workflow_id")
@click.pass_context
def workflow_run(ctx: click.Context, workflow_id: str):
    """Immediately run a workflow by ID via the daemon task queue."""
    vault_path: Path | None = None
    try:
        vault_obj = ctx.obj.get("vault") if ctx.obj else None
        if vault_obj:
            vault_path = vault_obj.path
    except Exception:
        pass

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

    vault_dir = str(vault_path) if vault_path else "."
    task = {
        "type": "task",
        "id": f"{workflow_id}_manual_{int(time.time())}",
        "task_type": "workflow",
        "workflow_id": workflow_id,
        "env": {"PKM_VAULT_DIR": vault_dir},
    }
    queue.append(task)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps(queue), encoding="utf-8")

    _console.print(
        f"[green]Queued workflow[/green] [bold]{workflow_id}[/bold] → task id: {task['id']}"
    )
