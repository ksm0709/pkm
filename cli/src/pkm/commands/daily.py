"""Daily note commands."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click
from rich.console import Console

console = Console()

DAILY_TEMPLATE = """\
---
id: {date}
aliases: []
tags:
  - daily-notes
---

## TODO
"""


@click.group(invoke_without_command=True)
@click.pass_context
def daily(ctx: click.Context) -> None:
    """Manage daily notes."""
    if ctx.invoked_subcommand is not None:
        return
    vault = ctx.obj["vault"]
    today = datetime.now().strftime("%Y-%m-%d")
    note_path = vault.daily_dir / f"{today}.md"
    if note_path.exists():
        console.print(note_path.read_text(encoding="utf-8"), end="")
    else:
        vault.daily_dir.mkdir(parents=True, exist_ok=True)
        content = DAILY_TEMPLATE.format(date=today)
        note_path.write_text(content, encoding="utf-8")
        console.print(content, end="")


@daily.command()
@click.argument("text")
@click.pass_context
def add(ctx: click.Context, text: str) -> None:
    """Append a timestamped log entry before ## TODO."""
    vault = ctx.obj["vault"]
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M")
    note_path = vault.daily_dir / f"{today}.md"

    if not note_path.exists():
        vault.daily_dir.mkdir(parents=True, exist_ok=True)
        note_path.write_text(DAILY_TEMPLATE.format(date=today), encoding="utf-8")

    content = note_path.read_text(encoding="utf-8")
    entry = f"- [{now}] {text}\n"

    if "## TODO" in content:
        content = content.replace("## TODO", f"{entry}## TODO", 1)
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += entry

    note_path.write_text(content, encoding="utf-8")
    console.print(f"Added: {entry}", end="")


@daily.command()
@click.argument("text")
@click.pass_context
def todo(ctx: click.Context, text: str) -> None:
    """Append a timestamped TODO entry after ## TODO."""
    vault = ctx.obj["vault"]
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M")
    note_path = vault.daily_dir / f"{today}.md"

    if not note_path.exists():
        vault.daily_dir.mkdir(parents=True, exist_ok=True)
        note_path.write_text(DAILY_TEMPLATE.format(date=today), encoding="utf-8")

    content = note_path.read_text(encoding="utf-8")
    entry = f"- [{now}] {text}\n"

    if "## TODO" in content:
        # Insert after the ## TODO line
        lines = content.splitlines(keepends=True)
        result = []
        inserted = False
        for i, line in enumerate(lines):
            result.append(line)
            if not inserted and line.rstrip("\n") == "## TODO":
                result.append(entry)
                inserted = True
        content = "".join(result)
        if not inserted:
            if not content.endswith("\n"):
                content += "\n"
            content += entry
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += entry

    note_path.write_text(content, encoding="utf-8")
    console.print(f"Added TODO: {entry}", end="")
