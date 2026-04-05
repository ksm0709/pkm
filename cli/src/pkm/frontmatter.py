"""YAML frontmatter parsing and generation for Obsidian markdown files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


_FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass
class Note:
    path: Path
    meta: dict = field(default_factory=dict)
    body: str = ""

    @property
    def id(self) -> str:
        return self.meta.get("id", self.path.stem)

    @property
    def tags(self) -> list[str]:
        return self.meta.get("tags", [])

    @property
    def aliases(self) -> list[str]:
        return self.meta.get("aliases", [])

    @property
    def title(self) -> str:
        return self.meta.get("title", self.path.stem)


def parse(path: Path) -> Note:
    text = path.read_text(encoding="utf-8")
    m = _FM_PATTERN.match(text)
    if m:
        meta = yaml.safe_load(m.group(1)) or {}
        body = text[m.end():]
    else:
        meta = {}
        body = text
    return Note(path=path, meta=meta, body=body)


def render(meta: dict, body: str) -> str:
    fm = yaml.dump(meta, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return f"---\n{fm}---\n\n{body}"


def generate_frontmatter(
    note_id: str,
    tags: list[str] | None = None,
    aliases: list[str] | None = None,
    **extra,
) -> dict:
    meta: dict = {"id": note_id, "aliases": aliases or [], "tags": tags or []}
    meta.update(extra)
    return meta
