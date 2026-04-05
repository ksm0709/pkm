"""pkm memory command group — agent memory store/search/session."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml

from pkm._memory_types import MEMORY_TYPES, SOURCE_TYPE_AGENT
from pkm.frontmatter import generate_memory_frontmatter


@click.group()
def memory() -> None:
    """Agent memory operations: store, search, session."""


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------

@memory.command()
@click.argument("content", required=False, default=None)
@click.option("--stdin", "use_stdin", is_flag=True, help="Read content from stdin")
@click.option(
    "--type", "memory_type",
    type=click.Choice(MEMORY_TYPES),
    required=True,
    help="Memory type",
)
@click.option("--importance", type=click.IntRange(1, 10), default=5, show_default=True)
@click.option("--session", "session_id", default=None, help="Session ID")
@click.option("--agent", "agent_id", default=None, help="Agent ID")
@click.option("--tags", "-t", default="", help="Comma-separated tags")
@click.pass_context
def store(
    ctx: click.Context,
    content: str | None,
    use_stdin: bool,
    memory_type: str,
    importance: int,
    session_id: str | None,
    agent_id: str | None,
    tags: str,
) -> None:
    """Store a memory as an atomic note.

    \b
    Examples:
      pkm memory store "learned X" --type semantic --importance 7
      echo "multi-line" | pkm memory store --stdin --type episodic --importance 5
    """
    if use_stdin:
        content = sys.stdin.read().strip()
    if not content:
        raise click.UsageError("Provide content as argument or use --stdin")

    vault = ctx.obj["vault"]
    notes_dir: Path = vault.notes_dir
    notes_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    date_prefix = now.strftime("%Y-%m-%d")
    slug = re.sub(r"[^\w\s-]", "", content[:40].lower()).strip()
    slug = re.sub(r"[\s_]+", "-", slug).strip("-") or "memory"
    note_id = f"{date_prefix}-{slug}"

    note_path = notes_dir / f"{note_id}.md"
    counter = 1
    while note_path.exists():
        note_path = notes_dir / f"{note_id}-{counter}.md"
        counter += 1

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    fm = generate_memory_frontmatter(
        note_id=note_path.stem,
        memory_type=memory_type,
        importance=float(importance),
        created_at=now.isoformat(),
        session_id=session_id,
        agent_id=agent_id,
        source_type=SOURCE_TYPE_AGENT,
        tags=tag_list,
    )
    frontmatter_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
    note_path.write_text(f"---\n{frontmatter_str}---\n\n{content}\n", encoding="utf-8")
    click.echo(str(note_path))


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@dataclass
class MemorySearchResult:
    path: str
    title: str
    score: float
    memory_type: str
    importance: float


def _scan_memory_notes(notes_dir: Path) -> list[dict]:
    """Scan notes/ for files with memory_type in frontmatter."""
    results = []
    if not notes_dir.is_dir():
        return results
    for md_file in sorted(notes_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        end = text.find("---", 3)
        if end == -1:
            continue
        try:
            fm = yaml.safe_load(text[3:end]) or {}
        except Exception:
            continue
        if "memory_type" not in fm:
            continue
        results.append({
            "path": str(md_file),
            "title": fm.get("id", md_file.stem),
            "memory_type": fm.get("memory_type", ""),
            "importance": float(fm.get("importance", 5.0)),
            "created_at": fm.get("created_at", ""),
            "session_id": fm.get("session_id"),
            "body": text[end + 3:].strip(),
            "fm": fm,
        })
    return results


def _score_memory(note: dict, query: str, recency_weight: float) -> float:
    """Simple relevance + recency + importance score."""
    import math

    body = note["body"].lower()
    title = note["title"].lower()
    q = query.lower()

    # Text match score (0..1)
    words = q.split()
    hit_count = sum(1 for w in words if w in body or w in title)
    text_score = hit_count / max(len(words), 1)

    # Recency score (0..1) — decay over 30 days
    recency_score = 0.0
    created_at = note.get("created_at", "")
    if created_at:
        try:
            dt = datetime.fromisoformat(str(created_at))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
            recency_score = math.exp(-age_days / 30)
        except (ValueError, TypeError):
            pass

    # Importance score (normalise 1-10 → 0..1)
    importance_score = (note["importance"] - 1) / 9.0

    relevance_weight = 1.0 - recency_weight
    return relevance_weight * (0.7 * text_score + 0.3 * importance_score) + recency_weight * recency_score


@memory.command()
@click.argument("query")
@click.option(
    "--type", "memory_type",
    type=click.Choice(MEMORY_TYPES),
    default=None,
    help="Filter by memory type",
)
@click.option(
    "--recency-weight",
    type=click.FloatRange(0.0, 1.0),
    default=0.3,
    show_default=True,
    help="Weight for recency vs relevance (0=relevance only, 1=recency only)",
)
@click.option("--min-importance", type=click.IntRange(1, 10), default=1)
@click.option("--top", "-n", default=10, show_default=True, help="Number of results")
@click.option(
    "--format", "output_format",
    type=click.Choice(["table", "plain", "json"]),
    default="table",
)
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    memory_type: str | None,
    recency_weight: float,
    min_importance: int,
    top: int,
    output_format: str,
) -> None:
    """Search memories with time-weighted scoring."""
    vault = ctx.obj["vault"]
    notes = _scan_memory_notes(vault.notes_dir)

    # Filter
    if memory_type:
        notes = [n for n in notes if n["memory_type"] == memory_type]
    notes = [n for n in notes if n["importance"] >= min_importance]

    # Score and rank
    scored = sorted(
        notes,
        key=lambda n: _score_memory(n, query, recency_weight),
        reverse=True,
    )[:top]

    if output_format == "json":
        click.echo(json.dumps(
            [
                {
                    "path": n["path"],
                    "title": n["title"],
                    "memory_type": n["memory_type"],
                    "importance": n["importance"],
                    "score": _score_memory(n, query, recency_weight),
                }
                for n in scored
            ],
            default=str,
        ))
    elif output_format == "plain":
        for n in scored:
            score = _score_memory(n, query, recency_weight)
            click.echo(f"{score:.3f}  {n['title']}  [{n['path']}]")
    else:
        if not scored:
            click.echo("No results found.")
            return
        click.echo(f"{'Score':>6}  {'Type':>10}  {'Imp':>3}  Title")
        click.echo("-" * 60)
        for n in scored:
            score = _score_memory(n, query, recency_weight)
            click.echo(f"{score:>6.3f}  {n['memory_type']:>10}  {n['importance']:>3.0f}  {n['title']}")


# ---------------------------------------------------------------------------
# session
# ---------------------------------------------------------------------------

@memory.command()
@click.argument("session_id")
@click.option(
    "--format", "output_format",
    type=click.Choice(["table", "plain", "json"]),
    default="table",
)
@click.pass_context
def session(ctx: click.Context, session_id: str, output_format: str) -> None:
    """List all memories for a given session ID."""
    vault = ctx.obj["vault"]
    notes = _scan_memory_notes(vault.notes_dir)
    matches = [n for n in notes if n["fm"].get("session_id") == session_id]

    if output_format == "json":
        click.echo(json.dumps(
            [
                {
                    "path": m["path"],
                    "title": m["title"],
                    "memory_type": m["memory_type"],
                    "importance": m["importance"],
                    "created_at": m["created_at"],
                }
                for m in matches
            ],
            default=str,
        ))
    elif output_format == "plain":
        for m in matches:
            click.echo(f"{m['created_at']}  {m['title']}")
    else:
        if not matches:
            click.echo(f"No memories found for session: {session_id}")
            return
        click.echo(f"{'Created':>32}  {'Type':>10}  {'Imp':>3}  Title")
        click.echo("-" * 70)
        for m in matches:
            click.echo(
                f"{str(m['created_at']):>32}  {m['memory_type']:>10}"
                f"  {m['importance']:>3.0f}  {m['title']}"
            )
