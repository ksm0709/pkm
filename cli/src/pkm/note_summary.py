"""Shared helpers for note descriptions and markdown body summaries."""

from __future__ import annotations

from typing import Any


def strip_leading_frontmatter(text: str) -> str:
    """Remove consecutive leading YAML frontmatter blocks from markdown text."""
    if not text.startswith("---"):
        return text

    remaining = text
    stripped_any = False
    while remaining.startswith("---"):
        lines = remaining.splitlines()
        if not lines or lines[0].strip() != "---":
            break
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() in {"---", "..."}:
                remaining = "\n".join(lines[index + 1 :]).lstrip()
                stripped_any = True
                break
        else:
            break
    return remaining if stripped_any else text


def _looks_like_frontmatter_fragment(text: str) -> bool:
    """Detect YAML metadata fragments that lost their delimiter lines."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    metadata_keys = {
        "id",
        "title",
        "aliases",
        "tags",
        "created_at",
        "updated_at",
        "importance",
        "memory_type",
        "source_type",
        "consolidated",
        "session_id",
        "agent_id",
    }
    metadata_lines = 0
    for line in lines[:8]:
        key = line.split(":", 1)[0].strip()
        if key in metadata_keys:
            metadata_lines += 1
    return metadata_lines >= 2 and metadata_lines >= min(len(lines), 4) // 2


def clean_description_text(text: str) -> str:
    """Return UI-safe description text with frontmatter artifacts removed."""
    cleaned = strip_leading_frontmatter(text).strip()
    if _looks_like_frontmatter_fragment(cleaned):
        return ""
    return cleaned


def note_description(meta: dict[str, Any] | None, body: str = "", max_len: int = 200) -> str:
    """Use explicit description or summarize body while skipping metadata."""
    raw = (meta or {}).get("description")
    if raw:
        cleaned = clean_description_text(str(raw))
        if cleaned:
            return cleaned

    body_text = clean_description_text(body)
    if not body_text:
        return ""
    summary = body_text[:max_len].replace("\n", " ").strip()
    return summary + ("..." if len(body_text) > max_len else "")
