"""pkm consolidate command — identify and mark daily notes for dream consolidation."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import click
import yaml


@click.group(invoke_without_command=True)
@click.pass_context
def consolidate(ctx: click.Context) -> None:
    """List daily notes eligible for consolidation.

    Run without subcommand to list candidates.
    Use 'mark' subcommand to mark a daily note as consolidated.
    """
    if ctx.invoked_subcommand is None:
        _list_candidates(ctx)


def _list_candidates(ctx: click.Context) -> None:
    """List daily notes that can be consolidated (not today, not already consolidated)."""
    vault = ctx.obj["vault"]
    daily_dir = vault.daily_dir

    if not daily_dir.exists():
        click.echo("No daily/ directory found.")
        return

    today = date.today().isoformat()
    candidates = []

    for md_file in sorted(daily_dir.glob("*.md"), reverse=True):
        date_str = md_file.stem  # expects YYYY-MM-DD
        if date_str == today:
            continue  # Skip today — still in use

        text = md_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)

        if fm.get("consolidated", False):
            continue  # Already consolidated

        # Count entries (lines starting with -, *, or [)
        body_start = text.find("---", 3)
        body = text[body_start + 3:] if body_start != -1 else text
        entry_count = sum(
            1 for line in body.splitlines()
            if line.strip().startswith(("-", "*", "["))
        )

        candidates.append({
            "date": date_str,
            "path": str(md_file),
            "entry_count": entry_count,
        })

    if not candidates:
        click.echo("No daily notes eligible for consolidation.")
        return

    click.echo(f"{'Date':>12}  {'Entries':>7}  Path")
    click.echo("-" * 60)
    for c in candidates:
        click.echo(f"{c['date']:>12}  {c['entry_count']:>7}  {c['path']}")
    click.echo(f"\n{len(candidates)} note(s) eligible. Run: pkm consolidate mark <date>")


@consolidate.command()
@click.argument("date_str")
@click.pass_context
def mark(ctx: click.Context, date_str: str) -> None:
    """Mark a daily note as consolidated.

    DATE_STR should be YYYY-MM-DD format.

    Example:
      pkm consolidate mark 2026-04-04
    """
    vault = ctx.obj["vault"]
    note_path = vault.daily_dir / f"{date_str}.md"

    if not note_path.exists():
        raise click.ClickException(f"Daily note not found: {note_path}")

    today = date.today().isoformat()
    if date_str == today:
        raise click.ClickException(
            "Cannot mark today's daily note as consolidated — it's still in use."
        )

    text = note_path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)

    if fm.get("consolidated", False):
        click.echo(f"Already consolidated: {note_path}")
        return

    new_text = _set_frontmatter_field(text, "consolidated", True)
    note_path.write_text(new_text, encoding="utf-8")
    click.echo(f"Marked as consolidated: {note_path}")


def _parse_frontmatter(text: str) -> dict:
    """Parse YAML frontmatter from markdown text. Returns empty dict if none."""
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(text[3:end]) or {}
    except Exception:
        return {}


def _set_frontmatter_field(text: str, key: str, value: object) -> str:
    """Set a field in YAML frontmatter, preserving the rest of the document."""
    if not text.startswith("---"):
        fm_str = yaml.dump({key: value}, allow_unicode=True, default_flow_style=False)
        return f"---\n{fm_str}---\n\n{text}"

    end = text.find("---", 3)
    if end == -1:
        return text  # Malformed — don't modify

    fm_text = text[3:end]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except Exception:
        return text  # Can't parse — don't corrupt

    fm[key] = value
    new_fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False)
    after_fm = text[end + 3:]
    return f"---\n{new_fm_str}---{after_fm}"
