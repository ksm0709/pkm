import os
import hashlib
import difflib
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from tiny_agent.tools import tool
from pkm.config import VaultConfig
from pkm.commands.notes import create_note, _search_notes
from pkm.note_lifecycle import rename_note_id


def _get_vault(vault_dir: str) -> VaultConfig:
    return VaultConfig(name=Path(vault_dir).name, path=Path(vault_dir))


def _note_hash(meta: dict[str, Any], body: str) -> str:
    from pkm.frontmatter import render

    return hashlib.sha256(render(meta, body).encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _find_note_path(vault: VaultConfig, note_id: str) -> Path | None:
    for base_dir in [vault.notes_dir, vault.daily_dir]:
        path = base_dir / f"{note_id}.md"
        if path.exists():
            return path
    return None


def _patch_error(
    note_id: str,
    operation: str,
    summary: str,
    *,
    matches: int | None = None,
) -> dict[str, Any]:
    return {
        "status": "error",
        "note_id": note_id,
        "operation": operation,
        "changed": False,
        "matches": matches,
        "summary": summary,
        "diff_preview": "",
    }


def _diff_preview(before: str, after: str, *, limit: int = 1600) -> str:
    diff = "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )
    return diff[:limit]


def _section_bounds(body: str, section: str) -> tuple[int, int, int] | None:
    import re

    target = section.strip().lower()
    if not target:
        return None
    pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
    for match in pattern.finditer(body):
        title = match.group(2).strip().rstrip("#").strip().lower()
        if title != target:
            continue
        level = len(match.group(1))
        next_match = None
        for candidate in pattern.finditer(body, match.end()):
            if len(candidate.group(1)) <= level:
                next_match = candidate
                break
        return match.start(), match.end(), next_match.start() if next_match else len(body)
    return None


def _normalize_block(text: str) -> str:
    return text.strip("\n")


def _append_to_body(body: str, new: str, section: str | None) -> str:
    block = _normalize_block(new)
    if section is None:
        if not body.endswith("\n"):
            body += "\n"
        return f"{body}{block}\n"

    bounds = _section_bounds(body, section)
    if bounds is None:
        raise ValueError(f"Section '{section}' not found.")
    _heading_start, _heading_end, section_end = bounds
    insert_at = section_end
    prefix = body[:insert_at].rstrip("\n")
    suffix = body[insert_at:]
    return f"{prefix}\n{block}\n{suffix}"


def _prepend_to_body(body: str, new: str, section: str | None) -> str:
    block = _normalize_block(new)
    if section is None:
        return f"{block}\n{body}"

    bounds = _section_bounds(body, section)
    if bounds is None:
        raise ValueError(f"Section '{section}' not found.")
    _heading_start, heading_end, _section_end = bounds
    rest = body[heading_end:]
    leading_newlines = len(rest) - len(rest.lstrip("\n"))
    insert_at = heading_end + leading_newlines
    return f"{body[:insert_at]}{block}\n{body[insert_at:]}"


def _upsert_section(body: str, section: str, new: str) -> str:
    heading = section.strip()
    if not heading:
        raise ValueError("section is required for upsert_section.")
    block = _normalize_block(new)
    bounds = _section_bounds(body, heading)
    replacement = f"## {heading}\n\n{block}\n"
    if bounds is None:
        if not body.endswith("\n"):
            body += "\n"
        return f"{body}\n{replacement}"

    start, _heading_end, section_end = bounds
    suffix = body[section_end:]
    if suffix and not suffix.startswith("\n"):
        suffix = "\n" + suffix
    return f"{body[:start]}{replacement}{suffix}"


def _patch_note_impl(
    vault: VaultConfig,
    note_id: str,
    operation: str,
    old: str | None = None,
    new: str | None = None,
    section: str | None = None,
    fields: dict[str, Any] | None = None,
    expected_occurrences: int = 1,
    base_hash: str | None = None,
) -> dict[str, Any]:
    path = _find_note_path(vault, note_id)
    if path is None:
        return _patch_error(note_id, operation, f"Note '{note_id}' not found.")

    from pkm.commands.notes import _append_operation_log
    from pkm.frontmatter import parse, render

    try:
        note = parse(path)
        result_note_id = str(note.id)
        meta = dict(note.meta or {})
        before_body = note.body
        current_hash = _note_hash(meta, before_body)
        if base_hash is not None and base_hash != current_hash:
            return _patch_error(
                note_id,
                operation,
                "Stale note content: base_hash does not match current note.",
            )

        matches: int | None = None
        if operation == "replace":
            if old is None or new is None:
                return _patch_error(note_id, operation, "old and new are required.")
            matches = before_body.count(old)
            if matches != expected_occurrences:
                return _patch_error(
                    note_id,
                    operation,
                    (
                        f"Expected {expected_occurrences} match(es) for patch text, "
                        f"found {matches}."
                    ),
                    matches=matches,
                )
            after_body = before_body.replace(old, new)
        elif operation == "append":
            if new is None:
                return _patch_error(note_id, operation, "new is required.")
            after_body = _append_to_body(before_body, new, section)
        elif operation == "prepend":
            if new is None:
                return _patch_error(note_id, operation, "new is required.")
            after_body = _prepend_to_body(before_body, new, section)
        elif operation == "upsert_section":
            if section is None or new is None:
                return _patch_error(
                    note_id, operation, "section and new are required."
                )
            after_body = _upsert_section(before_body, section, new)
        elif operation == "frontmatter":
            if not fields:
                return _patch_error(note_id, operation, "fields is required.")
            meta.update(fields)
            after_body = before_body
        else:
            return _patch_error(note_id, operation, f"Unsupported operation: {operation}")
    except ValueError as e:
        return _patch_error(note_id, operation, str(e))
    except Exception as e:
        return _patch_error(note_id, operation, f"Patch failed: {e}")

    changed = meta != dict(note.meta or {}) or after_body != before_body
    if not changed:
        return {
            "status": "unchanged",
            "note_id": result_note_id,
            "operation": operation,
            "changed": False,
            "matches": matches,
            "summary": "Patch made no changes.",
            "diff_preview": "",
        }

    path.write_text(render(meta, after_body), encoding="utf-8")
    _append_operation_log(vault, "patch", result_note_id, note.title)
    return {
        "status": "patched",
        "note_id": result_note_id,
        "operation": operation,
        "changed": True,
        "matches": matches,
        "summary": f"Patched note '{result_note_id}'.",
        "diff_preview": _diff_preview(before_body, after_body),
    }


@tool()
def add_note(
    title: str,
    content: str,
    tags: list[str] | None = None,
    memory_type: str | None = None,
    importance: int | None = None,
) -> str:
    """Create a new atomic note in the vault.

    Args:
        title: The title of the note.
        content: The body content of the note.
        tags: Optional list of tags.
        memory_type: Optional memory type (e.g., 'semantic', 'episodic', 'procedural').
        importance: Optional importance score (1-10).
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)
    try:
        note_path = create_note(
            vault=vault,
            title=title,
            content=content,
            tags=tags,
            memory_type=memory_type,
            importance=importance,
        )
        return f"Successfully created note at {note_path}"
    except Exception as e:
        return f"Error creating note: {str(e)}"


@tool()
def search_notes(query: str) -> str:
    """Search notes by title (case-insensitive partial match).

    Args:
        query: The search query.
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)
    try:
        matches = _search_notes(vault, query)
        if not matches:
            return f"No notes found matching '{query}'"

        results = [
            f"Title: {n.title}\nID: {n.id}\nContent:\n{n.body[:200]}..."
            for n in matches[:5]
        ]
        return "\n\n".join(results)
    except Exception as e:
        return f"Error searching notes: {str(e)}"


@tool()
def read_note(note_id: str) -> dict:
    """Read the full content and metadata of a note.

    Returns a dict with keys: note_id, title, body, frontmatter, created, updated,
    tags, importance.

    Args:
        note_id: The ID of the note (typically the filename without .md).
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)

    for base_dir in [vault.notes_dir, vault.daily_dir]:
        path = base_dir / f"{note_id}.md"
        if path.exists():
            from pkm.frontmatter import parse

            note = parse(path)
            fm = note.meta if note.meta else {}
            importance_raw = fm.get("importance")
            importance = int(importance_raw) if importance_raw is not None else None
            return {
                "note_id": str(note.id),
                "title": note.title,
                "body": note.body,
                "frontmatter": _json_safe(fm),
                "created": fm.get("created_at") or fm.get("source") or None,
                "updated": fm.get("updated_at") or None,
                "tags": note.tags,
                "importance": importance,
                "content_hash": _note_hash(fm, note.body),
            }

    return {"error": f"Note '{note_id}' not found."}


@tool()
def list_notes(filter: str | None = None, vault: str | None = None) -> list:
    """List notes in the vault, optionally filtered by title substring.

    Returns a list of dicts with keys: note_id, title, path, tags, created_at.

    Args:
        filter: Optional case-insensitive title filter (partial match).
        vault: Optional vault directory path (uses PKM_VAULT_DIR env if not provided).
    """
    v_dir = vault or os.environ.get("PKM_VAULT_DIR", ".")
    vault_obj = _get_vault(v_dir)

    from pkm.frontmatter import parse as _parse

    results = []
    if not vault_obj.notes_dir.is_dir():
        return results

    filter_lower = filter.lower() if filter else None
    for md_file in sorted(vault_obj.notes_dir.glob("*.md")):
        try:
            note = _parse(md_file)
            if filter_lower and filter_lower not in note.title.lower():
                continue
            fm = note.meta if note.meta else {}
            results.append(
                {
                    "note_id": note.id,
                    "title": note.title,
                    "path": str(md_file),
                    "tags": note.tags,
                    "created_at": fm.get("created_at") or fm.get("source") or None,
                }
            )
        except Exception:
            pass
    return results


@tool()
def update_note(note_id: str, content: str, tags: list[str] | None = None) -> str:
    """Replace the full body and optionally tags of an existing note.

    Args:
        note_id: The ID of the note.
        content: The new full content of the note.
        tags: Optional new list of tags to replace the old ones.
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)

    for base_dir in [vault.notes_dir, vault.daily_dir]:
        path = base_dir / f"{note_id}.md"
        if path.exists():
            from pkm.frontmatter import parse, render

            note = parse(path)
            if tags is not None:
                note.meta["tags"] = tags
            new_text = render(note.meta, content)
            path.write_text(new_text, encoding="utf-8")
            from pkm.commands.notes import _append_operation_log

            _append_operation_log(vault, "update", note.id, note.title)
            return f"Successfully updated note '{note_id}'"

    return f"Error: Note '{note_id}' not found."


@tool()
def patch_note(
    note_id: str,
    operation: Literal["replace", "append", "prepend", "upsert_section", "frontmatter"],
    old: str | None = None,
    new: str | None = None,
    section: str | None = None,
    fields: dict[str, Any] | None = None,
    expected_occurrences: int = 1,
    base_hash: str | None = None,
) -> dict[str, Any]:
    """Patch part of a note without replacing the full body.

    Use this for partial note edits. Use update_note only when replacing the entire
    body is intended.
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)
    return _patch_note_impl(
        vault,
        note_id=note_id,
        operation=operation,
        old=old,
        new=new,
        section=section,
        fields=fields,
        expected_occurrences=expected_occurrences,
        base_hash=base_hash,
    )


@tool()
def rename_note(old_note_id: str, new_note_id: str) -> dict:
    """Rename a note ID and update every wikilink that points to it.

    Args:
        old_note_id: Current note ID, without .md.
        new_note_id: New note ID, without .md.
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)
    try:
        result = rename_note_id(vault, old_note_id, new_note_id)
        return {
            "status": "renamed",
            "old_note_id": result.old_note_id,
            "new_note_id": result.new_note_id,
            "old_path": result.old_path,
            "new_path": result.new_path,
            "wikilinks_updated": result.wikilinks.replacements,
            "files_updated": result.wikilinks.changed_files,
        }
    except Exception as e:
        return {"error": str(e)}
