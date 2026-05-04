"""YAML frontmatter parsing and generation for Obsidian markdown files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


_FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_INLINE_TAG_PATTERN = re.compile(r"(?<![\w/])#([\w][\w/-]*)", re.UNICODE)


def _split_leading_frontmatter_blocks(text: str) -> tuple[list[dict[str, Any]], str]:
    """Return consecutive leading YAML blocks and the remaining markdown body."""
    blocks: list[dict[str, Any]] = []
    remaining = text

    while True:
        candidate = remaining.lstrip() if blocks else remaining
        match = _FM_PATTERN.match(candidate)
        if not match:
            return blocks, candidate if blocks else remaining

        meta = yaml.safe_load(match.group(1)) or {}
        blocks.append(meta if isinstance(meta, dict) else {})
        remaining = candidate[match.end() :]


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _merge_frontmatter_blocks(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    merged = dict(blocks[0]) if blocks else {}
    for block in blocks[1:]:
        for key, value in block.items():
            if key in {"tags", "aliases"}:
                existing = _as_list(merged.get(key))
                for item in _as_list(value):
                    if item not in existing:
                        existing.append(item)
                merged[key] = existing
            elif key not in merged or merged[key] in (None, "", [], {}):
                merged[key] = value
    return merged


def normalize_frontmatter_text(text: str) -> tuple[str, bool]:
    """Collapse accidental consecutive YAML blocks into one merged frontmatter."""
    blocks, body = _split_leading_frontmatter_blocks(text)
    if len(blocks) <= 1:
        return text, False
    return render(_merge_frontmatter_blocks(blocks), body), True


def extract_inline_tags(body: str) -> list[str]:
    """Extract Obsidian-style inline tags from markdown body text."""
    body_without_code = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
    tags: list[str] = []
    seen: set[str] = set()
    for match in _INLINE_TAG_PATTERN.finditer(body_without_code):
        tag = match.group(1).rstrip("/-")
        if not tag or tag.isdigit() or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


@dataclass
class Note:
    path: Path
    meta: dict[str, Any] = field(default_factory=dict)
    body: str = ""

    @property
    def id(self) -> str:
        return self.meta.get("id", self.path.stem)

    @property
    def tags(self) -> list[str]:
        raw = self.meta.get("tags", [])
        if isinstance(raw, str):
            frontmatter_tags = [t.strip() for t in raw.split(",") if t.strip()]
        else:
            frontmatter_tags = [str(t) for t in raw] if raw else []

        tags: list[str] = []
        seen: set[str] = set()
        for tag in [*frontmatter_tags, *extract_inline_tags(self.body)]:
            if tag and tag not in seen:
                seen.add(tag)
                tags.append(tag)
        return tags

    @property
    def aliases(self) -> list[str]:
        return self.meta.get("aliases", [])

    @property
    def description(self) -> str | None:
        return self.meta.get("description")

    @property
    def title(self) -> str:
        return self.meta.get("title", self.path.stem)


def parse(path: Path) -> Note:
    text = path.read_text(encoding="utf-8")
    blocks, body = _split_leading_frontmatter_blocks(text)
    if blocks:
        meta = blocks[0]
    else:
        meta = {}
        body = text
    return Note(path=path, meta=meta, body=body)


def render(meta: dict[str, Any], body: str) -> str:
    fm = yaml.dump(meta, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return f"---\n{fm}---\n\n{body}"


def generate_frontmatter(
    note_id: str,
    tags: list[str] | None = None,
    aliases: list[str] | None = None,
    description: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    meta: dict[str, Any] = {"id": note_id, "aliases": aliases or [], "tags": tags or []}
    if description is not None:
        meta["description"] = description
    meta.update(extra)
    return meta


def generate_memory_frontmatter(
    note_id: str,
    memory_type: str = "semantic",
    importance: float = 5.0,
    created_at: str | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
    source_type: str = "agent",
    consolidated: bool = False,
    tags: list[str] | None = None,
    aliases: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Generate YAML frontmatter for agent memory notes."""
    now = datetime.now(timezone.utc).isoformat()
    fm: dict[str, Any] = {
        "id": note_id,
        "memory_type": memory_type,
        "importance": float(importance),
        "created_at": created_at or now,
        "source_type": source_type,
        "consolidated": consolidated,
        "tags": tags or [],
        "aliases": aliases or [],
    }
    if session_id:
        fm["session_id"] = session_id
    if agent_id:
        fm["agent_id"] = agent_id
    fm.update(extra)
    return fm
