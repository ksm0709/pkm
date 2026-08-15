"""Feedback records stored as tagged daily subnotes."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from aiohttp import web

from pkm.commands.daily import DAILY_TEMPLATE, _add_subnote_link, _sanitize_title
from pkm.frontmatter import parse, render
from pkm.web.feedback_mail import send_feedback_email
from pkm.web.routes.notes import _resolve_vault
from pkm.web.security import request_same_origin_or_bearer_allowed

_FEEDBACK_TAG = "feedback"
_FEEDBACK_TYPES = {"requirement", "bug", "idea"}
_MAX_TITLE_LENGTH = 120
_MAX_DESCRIPTION_LENGTH = 8_000


def _guard_feedback_write(request: web.Request) -> None:
    if not request_same_origin_or_bearer_allowed(request):
        raise web.HTTPForbidden(
            reason="Feedback submissions require same-origin or bearer auth"
        )


def _required_text(
    data: dict[str, Any], field: str, *, maximum: int, single_line: bool = False
) -> str:
    value = data.get(field)
    if not isinstance(value, str):
        raise web.HTTPBadRequest(reason=f"Field '{field}' must be a string")
    value = value.strip()
    if not value:
        raise web.HTTPBadRequest(reason=f"Field '{field}' is required")
    if len(value) > maximum:
        raise web.HTTPBadRequest(
            reason=f"Field '{field}' must be at most {maximum} characters"
        )
    if "\0" in value or (
        single_line and ("\n" in value or "\r" in value or "\t" in value)
    ):
        raise web.HTTPBadRequest(reason=f"Field '{field}' contains invalid characters")
    return value


def _feedback_record(path: Path) -> dict[str, str]:
    note = parse(path)
    meta = note.meta or {}
    return {
        "note_id": str(note.id),
        "title": str(meta.get("title") or note.title),
        "description": note.body.strip(),
        "feedback_type": str(meta.get("feedback_type") or "requirement"),
        "created_at": str(meta.get("created_at") or ""),
    }


def _feedback_note_id(daily_dir: Path, today: str, title: str) -> str:
    slug = _sanitize_title(title)
    if not slug:
        raise web.HTTPBadRequest(reason="Field 'title' is empty after sanitization")

    base = f"{today}-feedback-{slug}"
    candidate = base
    suffix = 2
    while (daily_dir / f"{candidate}.md").exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


async def get_feedback(request: web.Request) -> web.Response:
    """GET /api/v1/vault/{name}/feedback — list feedback subnotes newest first."""
    vault = _resolve_vault(request.match_info["name"])
    if not vault.daily_dir.is_dir():
        return web.json_response([])

    records: list[dict[str, str]] = []
    for path in vault.daily_dir.glob("*.md"):
        try:
            note = parse(path)
        except Exception:
            continue
        if _FEEDBACK_TAG not in note.tags:
            continue
        records.append(_feedback_record(path))

    records.sort(key=lambda record: (record["created_at"], record["note_id"]), reverse=True)
    return web.json_response(records)


async def post_feedback(request: web.Request) -> web.Response:
    """POST /api/v1/vault/{name}/feedback — create a logged feedback subnote."""
    vault = _resolve_vault(request.match_info["name"])
    _guard_feedback_write(request)

    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON body")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(reason="JSON body must be an object")

    title = _required_text(data, "title", maximum=_MAX_TITLE_LENGTH, single_line=True)
    description = _required_text(data, "description", maximum=_MAX_DESCRIPTION_LENGTH)
    feedback_type = data.get("feedback_type", "requirement")
    if not isinstance(feedback_type, str) or feedback_type not in _FEEDBACK_TYPES:
        raise web.HTTPBadRequest(
            reason="Field 'feedback_type' must be requirement, bug, or idea"
        )

    now = datetime.now().astimezone()
    today = now.strftime("%Y-%m-%d")
    created_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    vault.daily_dir.mkdir(parents=True, exist_ok=True)
    note_id = _feedback_note_id(vault.daily_dir, today, title)
    feedback_path = vault.daily_dir / f"{note_id}.md"
    try:
        feedback_path.resolve().relative_to(vault.daily_dir.resolve())
    except ValueError:
        raise web.HTTPBadRequest(reason="Invalid feedback title")

    feedback_path.write_text(
        render(
            {
                "id": note_id,
                "title": title,
                "aliases": [],
                "tags": ["daily-note", _FEEDBACK_TAG],
                "feedback_type": feedback_type,
                "created_at": created_at,
            },
            description + "\n",
        ),
        encoding="utf-8",
    )

    daily_path = vault.daily_dir / f"{today}.md"
    if not daily_path.exists():
        daily_path.write_text(DAILY_TEMPLATE.format(date=today), encoding="utf-8")
    _add_subnote_link(daily_path, now.strftime("%H:%M:%S"), note_id)

    record = _feedback_record(feedback_path)
    delivery = await asyncio.to_thread(
        send_feedback_email,
        vault_name=vault.name,
        title=record["title"],
        description=record["description"],
        feedback_type=record["feedback_type"],
        created_at=record["created_at"],
    )
    record["email_status"] = delivery.status
    if delivery.recipient:
        record["email_recipient"] = delivery.recipient
    return web.json_response(record, status=201)
