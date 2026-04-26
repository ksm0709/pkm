"""Daily note commands."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
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
consolidated: false
aliases: []
tags:
- daily-notes
---
## Logs
"""


def _make_subnote_content(
    note_id: str,
    content: str = "",
    tags: list[str] | None = None,
    aliases: list[str] | None = None,
) -> str:
    """Generate subnote file content with frontmatter."""
    tags = tags or []
    aliases = aliases or []
    tags_yaml = "[]" if not tags else "\n" + "\n".join(f"- {t}" for t in tags)
    aliases_yaml = "[]" if not aliases else "\n" + "\n".join(f"- {a}" for a in aliases)
    return f"---\nid: {note_id}\naliases: {aliases_yaml}\ntags: {tags_yaml}\n---\n\n{content}"


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
    return title.strip("-").strip()


def add_daily_entry(vault, text: str) -> str:
    """Append a timestamped log entry to today's daily note. Click-free canonical implementation.

    Called by both the CLI ``daily add`` command and the MCP ``daily_add`` tool.
    Future changes to daily entry logic should target this function.

    Returns the formatted entry string.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M:%S")
    note_path = vault.daily_dir / f"{today}.md"

    vault.daily_dir.mkdir(parents=True, exist_ok=True)
    if not note_path.exists():
        note_path.write_text(DAILY_TEMPLATE.format(date=today), encoding="utf-8")

    content = note_path.read_text(encoding="utf-8")
    entry = f"- [{now}] {text}\n"

    if not content.endswith("\n"):
        content += "\n"
    content += entry

    note_path.write_text(content, encoding="utf-8")
    return entry


def _add_subnote_link(daily_path: Path, now: str, note_id: str) -> None:
    """Append a wikilink entry to the daily note."""
    content = daily_path.read_text(encoding="utf-8")
    entry = f"- [{now}] [[{note_id}]]\n"
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
@click.pass_context
def edit(ctx: click.Context) -> None:
    """Open today's daily note in an editor."""
    vault = ctx.obj["vault"]
    today = datetime.now().strftime("%Y-%m-%d")
    vault.daily_dir.mkdir(parents=True, exist_ok=True)

    config_data = load_config()
    editor_cmd = get_editor(config_data)

    note_path = vault.daily_dir / f"{today}.md"
    if not note_path.exists():
        note_path.write_text(DAILY_TEMPLATE.format(date=today), encoding="utf-8")

    result = subprocess.run([*shlex.split(editor_cmd), str(note_path)])
    if result.returncode != 0:
        console.print(f"[yellow]Editor exited with code {result.returncode}[/yellow]")


@daily.command()
@click.argument("text")
@click.option("--vault", "-v", "vault_name", default=None, help="Vault name")
@click.pass_context
def add(ctx: click.Context, text: str, vault_name: str | None) -> None:
    """Append a timestamped log entry to today's daily note."""
    if vault_name:
        from pkm.config import get_vault

        vault = get_vault(vault_name)
    else:
        vault = ctx.obj["vault"]

    add_daily_entry(vault, text)
    now = datetime.now().strftime("%H:%M:%S")
    console.print(f"Daily note added at [{now}].")


@daily.command()
@click.argument("title")
@click.option("--content", "content", default="", help="Subnote body content.")
@click.option(
    "--tags", "tags_str", default="", help='Comma-separated tags, e.g. "work,ideas".'
)
@click.option(
    "--aliases",
    "aliases_str",
    default="",
    help='Comma-separated aliases, e.g. "My Note,Alias".',
)
@click.option(
    "--stdin",
    "from_stdin",
    is_flag=True,
    default=False,
    help="Read content from stdin (mutually exclusive with --content).",
)
@click.pass_context
def subnote(
    ctx: click.Context,
    title: str,
    content: str,
    tags_str: str,
    aliases_str: str,
    from_stdin: bool,
) -> None:
    """Create a subnote and log a wikilink in today's daily note.

    The subnote YYYY-MM-DD-TITLE.md is created in the daily directory.
    If it already exists, only the wikilink is added to the daily log.

    \b
    Agent usage examples:
      pkm daily subnote "meeting" --content "# Meeting\\n- discussed roadmap" --tags "work,meeting"
      pkm daily subnote "todo" --tags "tasks" --aliases "TODOs"
      echo "# Ideas" | pkm daily subnote "ideas" --stdin
    """
    if from_stdin and content:
        raise click.UsageError("Cannot use both --content and --stdin.")

    vault = ctx.obj["vault"]
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M:%S")

    if from_stdin:
        content = sys.stdin.read()

    tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
    aliases = (
        [a.strip() for a in aliases_str.split(",") if a.strip()] if aliases_str else []
    )

    title_slug = _sanitize_title(title)
    if not title_slug:
        raise click.ClickException("Title cannot be empty.")

    note_id = f"{today}-{title_slug}"
    subnote_path = vault.daily_dir / f"{note_id}.md"

    vault.daily_dir.mkdir(parents=True, exist_ok=True)
    if not str(subnote_path.resolve()).startswith(str(vault.daily_dir.resolve())):
        raise click.ClickException(
            "Invalid title: would create file outside daily directory."
        )

    if not subnote_path.exists():
        subnote_path.write_text(
            _make_subnote_content(note_id, content, tags, aliases), encoding="utf-8"
        )
        console.print(f"[green]Created:[/green] {subnote_path.name}")
    else:
        console.print(f"[dim]Sub-note exists:[/dim] {subnote_path.name}")

    daily_path = vault.daily_dir / f"{today}.md"
    if not daily_path.exists():
        daily_path.write_text(DAILY_TEMPLATE.format(date=today), encoding="utf-8")

    _add_subnote_link(daily_path, now, note_id)
    console.print(f"Logged: [[{note_id}]]")
