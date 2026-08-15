"""Shared note lifecycle operations.

All note ID/path-changing entrypoints should route through this module so
wikilinks are rewritten consistently across CLI, tools, MCP, and web code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pkm.annotations.store import (
    AnnotationSource,
    annotation_sidecar_path,
    note_lifecycle_lock,
    rename_annotation_document,
)
from pkm.config import VaultConfig
from pkm.frontmatter import parse, render
from pkm.wikilinks import WikilinkRewriteResult, rewrite_wikilinks_in_vault

_NOTE_ID_RE = re.compile(r"^[A-Za-z0-9가-힣@._-]{1,160}$")
_LEGACY_ANNOTATIONS_HEADING = "## Annotations"


def has_legacy_annotations_section(body: str) -> bool:
    """Return whether a note body still contains the retired legacy section."""

    return any(
        line.strip() == _LEGACY_ANNOTATIONS_HEADING for line in re.split(r"\r?\n", body)
    )


def strip_legacy_annotations_section(body: str) -> str:
    """Remove the reserved legacy annotations section from a parsed note body."""

    lines = re.split(r"\r?\n", body)
    heading_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() == _LEGACY_ANNOTATIONS_HEADING
        ),
        -1,
    )
    if heading_index < 0:
        return body

    end_index = len(lines)
    for index in range(heading_index + 1, len(lines)):
        if re.match(r"^#{1,6}\s+", lines[index]):
            end_index = index
            break

    start_index = heading_index
    while start_index > 0 and not lines[start_index - 1].strip():
        start_index -= 1
    retained = lines[:start_index] + lines[end_index:]
    while retained and not retained[-1].strip():
        retained.pop()
    return "\n".join(retained) + ("\n" if retained else "")


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
    """Rename a note and its sidecar under ordered lifecycle locks."""

    old_note_id = validate_note_id(old_note_id)
    new_note_id = validate_note_id(new_note_id)
    with note_lifecycle_lock(vault, old_note_id, new_note_id):
        return _rename_note_id_locked(
            vault,
            old_note_id,
            new_note_id,
            include_tags=include_tags,
        )


def _rename_note_id_locked(
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
    old_annotation_source = AnnotationSource(kind="note", identifier=old_note_id)
    new_annotation_source = AnnotationSource(kind="note", identifier=new_note_id)
    if annotation_sidecar_path(vault, new_annotation_source).exists():
        raise FileExistsError(f"Annotation sidecar for '{new_note_id}' already exists")

    destination.write_text(render(meta, note.body), encoding="utf-8")
    try:
        rename_annotation_document(vault, old_annotation_source, new_annotation_source)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
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
