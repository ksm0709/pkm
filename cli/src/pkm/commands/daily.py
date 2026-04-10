"""Daily note commands."""

from __future__ import annotations

import re
import shlex
import subprocess
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console

from pkm.config import load_config
from pkm.editor import get_editor

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

SUBNOTE_TEMPLATE = """\
---
id: {note_id}
aliases: []
tags: []
---

"""


def _get_subnotes(daily_dir: Path, date_str: str) -> list[Path]:
    """Return sub-notes for a given date, sorted alphabetically."""
    if not daily_dir.is_dir():
        return []
    return sorted(daily_dir.glob(f"{date_str}-*.md"))


def _sanitize_title(raw: str) -> str:
    """Sanitize a sub-note title: replace spaces with hyphens, strip path traversal."""
    title = raw.replace(" ", "-")
    title = re.sub(r"[/\\]", "", title)  # strip path separators
    title = re.sub(r"\.\.+", "", title)  # strip traversal sequences
    title = title.strip("-").strip()
    return title


def _add_subnote_link(daily_path: Path, now: str, note_id: str) -> None:
    """Insert a Sub note wikilink entry before ## TODO in the daily note."""
    content = daily_path.read_text(encoding="utf-8")
    entry = f"- [{now}] Sub note added: [[{note_id}]]\n"
    if "## TODO" in content:
        content = content.replace("## TODO", f"{entry}## TODO", 1)
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += entry
    daily_path.write_text(content, encoding="utf-8")


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

    subnotes = _get_subnotes(vault.daily_dir, today)
    for subnote in subnotes:
        title = subnote.stem[len(today) + 1 :]
        if not title:
            continue
        console.print(f"\n--- {title} ---")
        console.print(subnote.read_text(encoding="utf-8"), end="")


@daily.command()
@click.option(
    "--sub",
    "sub_title",
    is_flag=False,
    flag_value="",
    default=None,
    help="Create and edit a sub-note. Optionally provide a title directly.",
)
@click.pass_context
def edit(ctx: click.Context, sub_title: str | None) -> None:
    """Open today's daily note in an editor.

    Use --sub to create a sub-note interactively, or --sub <title> to skip the prompt.
    """
    vault = ctx.obj["vault"]
    today = datetime.now().strftime("%Y-%m-%d")
    vault.daily_dir.mkdir(parents=True, exist_ok=True)

    config_data = load_config()
    editor_cmd = get_editor(config_data)

    if sub_title is not None:
        if sub_title:
            raw_title = sub_title
        else:
            default_title = datetime.now().strftime("%H-%M")
            raw_title = click.prompt("Title", default=default_title)

        title = _sanitize_title(raw_title)
        if not title:
            raise click.ClickException("Title cannot be empty.")

        note_id = f"{today}-{title}"
        note_path = vault.daily_dir / f"{note_id}.md"

        # Guard against path traversal
        if not str(note_path.resolve()).startswith(str(vault.daily_dir.resolve())):
            raise click.ClickException(
                "Invalid title: would create file outside daily directory."
            )

        if not note_path.exists():
            note_path.write_text(
                SUBNOTE_TEMPLATE.format(note_id=note_id), encoding="utf-8"
            )
            console.print(f"[green]Created:[/green] {note_path.name}")
        else:
            console.print(f"[dim]Opening existing:[/dim] {note_path.name}")

        daily_path = vault.daily_dir / f"{today}.md"
        if not daily_path.exists():
            daily_path.write_text(DAILY_TEMPLATE.format(date=today), encoding="utf-8")
        _add_subnote_link(daily_path, datetime.now().strftime("%H:%M"), note_id)
    else:
        note_path = vault.daily_dir / f"{today}.md"
        if not note_path.exists():
            note_path.write_text(DAILY_TEMPLATE.format(date=today), encoding="utf-8")

    result = subprocess.run([*shlex.split(editor_cmd), str(note_path)])
    if result.returncode != 0:
        console.print(f"[yellow]Editor exited with code {result.returncode}[/yellow]")


@daily.command()
@click.argument("text", required=False, default=None)
@click.option(
    "--sub",
    "sub_title",
    is_flag=False,
    flag_value="",
    default=None,
    help="Create a sub-note and log a wikilink. Optionally provide a title directly.",
)
@click.pass_context
def add(ctx: click.Context, text: str | None, sub_title: str | None) -> None:
    """Append a timestamped log entry before ## TODO.

    Use --sub to create a sub-note and log a wikilink, or provide TEXT to log a plain entry.
    """
    if sub_title is not None and text is not None:
        raise click.UsageError("Cannot use both TEXT and --sub.")
    if sub_title is None and text is None:
        raise click.UsageError("Either TEXT or --sub is required.")

    vault = ctx.obj["vault"]
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M")
    note_path = vault.daily_dir / f"{today}.md"

    vault.daily_dir.mkdir(parents=True, exist_ok=True)
    if not note_path.exists():
        note_path.write_text(DAILY_TEMPLATE.format(date=today), encoding="utf-8")

    if sub_title is not None:
        if sub_title:
            raw_title = sub_title
        else:
            default_title = datetime.now().strftime("%H-%M")
            raw_title = click.prompt("Title", default=default_title)

        title = _sanitize_title(raw_title)
        if not title:
            raise click.ClickException("Title cannot be empty.")

        note_id = f"{today}-{title}"
        subnote_path = vault.daily_dir / f"{note_id}.md"

        if not str(subnote_path.resolve()).startswith(str(vault.daily_dir.resolve())):
            raise click.ClickException(
                "Invalid title: would create file outside daily directory."
            )

        if not subnote_path.exists():
            subnote_path.write_text(
                SUBNOTE_TEMPLATE.format(note_id=note_id), encoding="utf-8"
            )
            console.print(f"[green]Created:[/green] {subnote_path.name}")
        else:
            console.print(f"[dim]Sub-note exists:[/dim] {subnote_path.name}")

        _add_subnote_link(note_path, now, note_id)
        entry = f"- [{now}] Sub note added: [[{note_id}]]\n"
        console.print(f"Linked: {entry}", end="")
    else:
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
