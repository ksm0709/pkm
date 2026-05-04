"""Shared note lifecycle operations.

All note ID/path-changing entrypoints should route through this module so
wikilinks are rewritten consistently across CLI, tools, MCP, and web code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pkm.config import VaultConfig
from pkm.frontmatter import parse, render
from pkm.wikilinks import WikilinkRewriteResult, rewrite_wikilinks_in_vault

_NOTE_ID_RE = re.compile(r"^[A-Za-z0-9가-힣@._-]{1,160}$")


@dataclass(frozen=True)
class NoteRenameResult:
    old_note_id: str
    new_note_id: str
    old_path: str
    new_path: str
    wikilinks: WikilinkRewriteResult


def validate_note_id(note_id: str) -> str:
    """Validate a flat note ID used by lifecycle operations."""
    note_id = note_id.strip()
    if not note_id:
        raise ValueError("note_id cannot be empty")
    if note_id.startswith("tag:"):
        raise ValueError("tag pages are not note files")
    if "/" in note_id or "\\" in note_id or ".." in note_id:
        raise ValueError("note_id must be a flat filename stem")
    if note_id in {".", ".."} or not _NOTE_ID_RE.fullmatch(note_id):
        raise ValueError("note_id contains unsupported characters")
    return note_id


def note_directories(vault: VaultConfig, *, include_tags: bool = False) -> list[Path]:
    dirs = [vault.notes_dir, vault.daily_dir]
    if include_tags:
        dirs.append(vault.tags_dir)
    return dirs


def find_note_file(
    vault: VaultConfig,
    note_id: str,
    *,
    include_tags: bool = False,
) -> Path | None:
    """Find a note file by ID in vault note directories."""
    note_id = validate_note_id(note_id)
    for directory in note_directories(vault, include_tags=include_tags):
        path = directory / f"{note_id}.md"
        if path.exists():
            return path
    return None


def note_file_exists(
    vault: VaultConfig,
    note_id: str,
    *,
    include_tags: bool = False,
) -> bool:
    return find_note_file(vault, note_id, include_tags=include_tags) is not None


def rename_note_id(
    vault: VaultConfig,
    old_note_id: str,
    new_note_id: str,
    *,
    include_tags: bool = False,
) -> NoteRenameResult:
    """Rename a note ID and rewrite all wikilinks to the new target."""
    old_note_id = validate_note_id(old_note_id)
    new_note_id = validate_note_id(new_note_id)
    if old_note_id == new_note_id:
        raise ValueError("old_note_id and new_note_id are the same")

    source = find_note_file(vault, old_note_id, include_tags=include_tags)
    if source is None:
        raise FileNotFoundError(f"Note '{old_note_id}' not found")

    if note_file_exists(vault, new_note_id, include_tags=True):
        raise FileExistsError(f"Note '{new_note_id}' already exists")

    destination = source.with_name(f"{new_note_id}.md")
    note = parse(source)
    meta = dict(note.meta or {})
    meta["id"] = new_note_id

    destination.write_text(render(meta, note.body), encoding="utf-8")
    source.unlink()

    wikilinks = rewrite_wikilinks_in_vault(vault, old_note_id, new_note_id)
    _append_operation_log(vault, "rename", new_note_id, note.title)
    _update_index_best_effort(vault)

    return NoteRenameResult(
        old_note_id=old_note_id,
        new_note_id=new_note_id,
        old_path=str(source),
        new_path=str(destination),
        wikilinks=wikilinks,
    )


def _append_operation_log(
    vault: VaultConfig,
    operation: str,
    note_id: str,
    title: str,
) -> None:
    from pkm.commands.notes import _append_operation_log as append

    append(vault, operation, note_id, title)


def _update_index_best_effort(vault: VaultConfig) -> None:
    try:
        from pkm.search_engine import update_index_via_daemon

        update_index_via_daemon(vault)
    except Exception:
        pass
