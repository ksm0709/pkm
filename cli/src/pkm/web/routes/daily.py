"""Daily note REST handlers."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from aiohttp import web

from pkm.config import VaultConfig
from pkm.frontmatter import parse
from pkm.web.routes.notes import _json_safe, _resolve_vault

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_DAILY_TEMPLATE = """\
---
id: {date}
consolidated: false
aliases: []
tags:
- daily-notes
---
## Logs
"""


def _extract_snippet(content: str) -> str:
    """Return the first non-empty markdown line after the frontmatter block."""
    lines = content.splitlines()
    fm_end = 0
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                fm_end = i + 1
                break
    for line in lines[fm_end:]:
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _count_todos(content: str) -> int:
    """Count open checkboxes `- [ ]` in content."""
    return content.count("- [ ]")


def _daily_path(vault: VaultConfig, date_str: str) -> Path:
    return vault.daily_dir / f"{date_str}.md"


def _ensure_daily(vault: VaultConfig, date_str: str) -> Path:
    """Return the daily note path, creating the file if it does not exist."""
    path = _daily_path(vault, date_str)
    if not path.exists():
        vault.daily_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(_DAILY_TEMPLATE.format(date=date_str), encoding="utf-8")
    return path


def _daily_note_response(path: Path) -> dict:
    note = parse(path)
    fm = note.meta or {}
    importance_raw = fm.get("importance")
    # note.id and note.title may be datetime.date when YAML parses YYYY-MM-DD ids
    return {
        "note_id": str(note.id),
        "title": str(note.title),
        "body": note.body,
        "frontmatter": _json_safe(fm),
        "created": _json_safe(fm.get("created_at") or fm.get("source") or None),
        "updated": _json_safe(fm.get("updated_at") or None),
        "tags": note.tags,
        "importance": int(importance_raw) if importance_raw is not None else None,
    }


def _daily_summary(date_str: str, path: Path) -> dict:
    content = path.read_text(encoding="utf-8")
    note = parse(path)
    return {
        "date": date_str,
        "title": str(note.title),  # may be datetime.date for YYYY-MM-DD ids
        "todo_count": _count_todos(content),
        "snippet": _extract_snippet(content),
    }


async def get_daily_today(request: web.Request) -> web.Response:
    """GET /api/v1/vault/{name}/daily/today — return (or create) today's daily note."""
    vault = _resolve_vault(request.match_info["name"])
    today = datetime.now().strftime("%Y-%m-%d")
    path = _ensure_daily(vault, today)
    return web.json_response(_daily_note_response(path))


async def post_daily_today(request: web.Request) -> web.Response:
    """POST /api/v1/vault/{name}/daily/today — append an entry or create a subnote."""
    vault = _resolve_vault(request.match_info["name"])

    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON body")

    entry_type = data.get("type", "entry")
    content = data.get("content", "")

    if entry_type == "entry":
        from pkm.commands.daily import add_daily_entry

        entry = add_daily_entry(vault, content)
        return web.json_response({"entry": entry}, status=201)

    if entry_type == "subnote":
        title = data.get("title")
        if not title:
            raise web.HTTPBadRequest(
                reason="Field 'title' is required for type 'subnote'"
            )

        from pkm.commands.daily import (
            _add_subnote_link,
            _make_subnote_content,
            _sanitize_title,
        )

        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().strftime("%H:%M:%S")
        title_slug = _sanitize_title(title)
        if not title_slug:
            raise web.HTTPBadRequest(reason="'title' is empty after sanitization")

        note_id = f"{today}-{title_slug}"
        subnote_path = vault.daily_dir / f"{note_id}.md"
        vault.daily_dir.mkdir(parents=True, exist_ok=True)

        if not subnote_path.exists():
            subnote_path.write_text(
                _make_subnote_content(note_id, content), encoding="utf-8"
            )

        daily_path = _ensure_daily(vault, today)
        _add_subnote_link(daily_path, now, note_id)
        return web.json_response({"note_id": note_id}, status=201)

    raise web.HTTPBadRequest(reason="'type' must be 'entry' or 'subnote'")


async def get_daily_date(request: web.Request) -> web.Response:
    """GET /api/v1/vault/{name}/daily/{date} — return a specific date's daily note."""
    vault = _resolve_vault(request.match_info["name"])
    date_str = request.match_info["date"]

    if not _DATE_ONLY_RE.match(date_str):
        raise web.HTTPBadRequest(reason="'date' must be in YYYY-MM-DD format")

    path = _daily_path(vault, date_str)
    if not path.exists():
        raise web.HTTPNotFound(reason=f"No daily note for {date_str}")

    return web.json_response(_daily_note_response(path))


async def list_daily(request: web.Request) -> web.Response:
    """GET /api/v1/vault/{name}/daily — paginated daily note summaries (descending).

    Query params:
      before: YYYY-MM-DD  — exclusive upper bound (strictly older)
      limit:  int         — default 50, max 100
    """
    vault = _resolve_vault(request.match_info["name"])

    before = request.rel_url.query.get("before")
    try:
        limit = int(request.rel_url.query.get("limit", "50"))
    except ValueError:
        raise web.HTTPBadRequest(reason="'limit' must be an integer")
    limit = min(max(1, limit), 100)

    if before and not _DATE_ONLY_RE.match(before):
        raise web.HTTPBadRequest(reason="'before' must be in YYYY-MM-DD format")

    if not vault.daily_dir.is_dir():
        return web.json_response([])

    summaries = []
    for path in vault.daily_dir.glob("*.md"):
        stem = path.stem
        if not _DATE_ONLY_RE.match(stem):
            continue  # skip subnotes like YYYY-MM-DD-title.md
        if before and stem >= before:
            continue  # exclusive: skip dates >= before
        try:
            summaries.append(_daily_summary(stem, path))
        except Exception:
            pass

    summaries.sort(key=lambda s: s["date"], reverse=True)
    return web.json_response(summaries[:limit])
