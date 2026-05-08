"""Scenario tests for tiny-agent note tools."""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from pkm.frontmatter import parse


def _call_tool(fn, **kwargs):
    result = fn(**kwargs)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
    if isinstance(result, str):
        try:
            return json.loads(result)
        except (TypeError, ValueError):
            return result
    return result


def _write_note(path: Path, *, note_id: str, title: str, body: str, tags=None) -> None:
    tags = tags or []
    tag_lines = "\n".join(f"  - {tag}" for tag in tags)
    path.write_text(
        f"---\nid: {note_id}\ntitle: {title}\ntags:\n{tag_lines}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_add_note_creates_memory_note_and_reports_duplicate(
    tmp_vault, monkeypatch
) -> None:
    """add_note resolves PKM_VAULT_DIR, persists memory metadata, and reports collisions."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    from pkm.tools.notes import add_note

    result = _call_tool(
        add_note,
        title="Scenario Coverage",
        content="Body for the note",
        tags=["coverage", "tools"],
        memory_type="procedural",
        importance=8,
    )

    assert result.startswith("Successfully created note at ")
    note_path = Path(result.removeprefix("Successfully created note at "))
    assert note_path.exists()
    assert note_path.parent == tmp_vault.notes_dir

    note = parse(note_path)
    assert note.id == f"{date.today().isoformat()}-scenario-coverage"
    assert note.meta["memory_type"] == "procedural"
    assert note.meta["importance"] == 8.0
    assert note.tags == ["coverage", "tools"]
    assert "Body for the note" in note.body

    duplicate = _call_tool(
        add_note,
        title="Scenario Coverage",
        content="Different body",
    )
    assert duplicate.startswith("Error creating note:")
    assert "already exists" in duplicate


def test_search_notes_formats_top_five_matches_and_empty_or_error_paths(
    tmp_vault, monkeypatch
) -> None:
    """search_notes formats note previews, caps matches, and normalizes failures."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    for idx in range(6):
        _write_note(
            tmp_vault.notes_dir / f"scenario-{idx}.md",
            note_id=f"scenario-{idx}",
            title=f"Scenario Match {idx}",
            body=f"Body preview {idx}",
            tags=["search"],
        )

    from pkm.tools import notes as notes_tools

    result = _call_tool(notes_tools.search_notes, query="scenario match")

    assert result.count("Title: Scenario Match") == 5
    assert "Title: Scenario Match 0" in result
    assert "ID: scenario-0" in result
    assert "Content:\nBody preview 0" in result
    assert "..." in result
    assert "Title: Scenario Match 5" not in result

    no_match = _call_tool(notes_tools.search_notes, query="no such title")
    assert no_match == "No notes found matching 'no such title'"

    with patch.object(
        notes_tools, "_search_notes", side_effect=RuntimeError("search unavailable")
    ):
        error = _call_tool(notes_tools.search_notes, query="scenario")
    assert error == "Error searching notes: search unavailable"


def test_list_notes_uses_directory_override_filters_and_skips_bad_files(
    tmp_vault, tmp_path, monkeypatch
) -> None:
    """list_notes has a tiny-agent list contract and resilient parse behavior."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_path / "wrong-vault"))
    other_vault = tmp_path / "other-vault"
    notes_dir = other_vault / "notes"
    notes_dir.mkdir(parents=True)
    _write_note(
        notes_dir / "alpha.md",
        note_id="alpha",
        title="Alpha Scenario",
        body="Alpha body",
        tags=["one"],
    )
    _write_note(
        notes_dir / "beta.md",
        note_id="beta",
        title="Beta Note",
        body="Beta body",
        tags=["two"],
    )
    (notes_dir / "bad.md").write_text("---\n: bad: yaml\n---\n", encoding="utf-8")

    from pkm.tools.notes import list_notes

    filtered = _call_tool(
        list_notes,
        filter="ALPHA",
        vault=str(other_vault),
    )

    assert filtered == [
        {
            "note_id": "alpha",
            "title": "Alpha Scenario",
            "path": str(notes_dir / "alpha.md"),
            "tags": ["one"],
            "created_at": None,
        }
    ]

    all_notes = _call_tool(list_notes, vault=str(other_vault))
    assert {item["note_id"] for item in all_notes} == {"alpha", "beta"}

    missing = _call_tool(list_notes, vault=str(tmp_path / "missing-vault"))
    assert missing == []


def test_update_note_updates_regular_and_daily_notes_and_logs(
    tmp_vault, monkeypatch
) -> None:
    """update_note rewrites body/tags, searches daily notes too, and logs updates."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    from pkm.tools.notes import update_note

    result = _call_tool(
        update_note,
        note_id="2026-04-01-mvcc",
        content="Updated body #inline-tag",
        tags=["updated", "tools"],
    )

    assert result == "Successfully updated note '2026-04-01-mvcc'"
    note = parse(tmp_vault.notes_dir / "2026-04-01-mvcc.md")
    assert note.id == "2026-04-01-mvcc"
    assert note.meta["tags"] == ["updated", "tools"]
    assert "Updated body" in note.body
    assert "[update] 2026-04-01-mvcc" in (tmp_vault.pkm_dir / "log.md").read_text(
        encoding="utf-8"
    )

    daily_result = _call_tool(
        update_note,
        note_id="2026-04-01",
        content="Daily replacement body",
    )

    assert daily_result == "Successfully updated note '2026-04-01'"
    daily = parse(tmp_vault.daily_dir / "2026-04-01.md")
    assert str(daily.id) == "2026-04-01"
    assert "Daily replacement body" in daily.body

    missing = _call_tool(update_note, note_id="missing-note", content="Body")
    assert missing == "Error: Note 'missing-note' not found."


def test_rename_note_reports_real_missing_and_conflict_errors(
    tmp_vault, monkeypatch
) -> None:
    """rename_note returns error dicts for lifecycle missing/conflict failures."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    from pkm.tools.notes import rename_note

    missing = _call_tool(
        rename_note,
        old_note_id="does-not-exist",
        new_note_id="new-note",
    )
    assert "not found" in missing["error"]

    conflict = _call_tool(
        rename_note,
        old_note_id="database-isolation",
        new_note_id="2026-04-01-mvcc",
    )
    assert "already exists" in conflict["error"]
