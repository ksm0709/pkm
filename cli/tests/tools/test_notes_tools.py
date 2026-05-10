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


def test_patch_note_is_registered_for_tiny_agent_tools() -> None:
    """patch_note is exposed through the shared tiny-agent tool registry."""
    from pkm.tools import get_pkm_tools

    names = {getattr(tool, "__name__", "") for tool in get_pkm_tools()}
    assert "patch_note" in names


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


def test_patch_note_replaces_exact_body_fragment_and_rejects_ambiguous_matches(
    tmp_vault, monkeypatch
) -> None:
    """patch_note replaces a unique body fragment without rewriting unrelated content."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    from pkm.tools.notes import patch_note

    note_path = tmp_vault.notes_dir / "2026-04-01-mvcc.md"
    before = parse(note_path)

    result = _call_tool(
        patch_note,
        note_id="2026-04-01-mvcc",
        operation="replace",
        old="MVCC is a concurrency control technique.",
        new="MVCC lets readers and writers avoid blocking each other.",
    )

    assert result["status"] == "patched"
    assert result["changed"] is True
    assert result["matches"] == 1
    note = parse(note_path)
    assert note.meta == before.meta
    assert "MVCC lets readers and writers avoid blocking each other." in note.body
    assert "Related: [[2026-04-01]], [[database-isolation]]" in note.body
    assert "[patch] 2026-04-01-mvcc" in (tmp_vault.pkm_dir / "log.md").read_text(
        encoding="utf-8"
    )

    no_match = _call_tool(
        patch_note,
        note_id="2026-04-01-mvcc",
        operation="replace",
        old="missing fragment",
        new="unused",
    )
    assert no_match["status"] == "error"
    assert no_match["matches"] == 0
    assert "missing fragment" not in parse(note_path).body

    note_path.write_text(
        note_path.read_text(encoding="utf-8") + "\nduplicate\nduplicate\n",
        encoding="utf-8",
    )
    ambiguous = _call_tool(
        patch_note,
        note_id="2026-04-01-mvcc",
        operation="replace",
        old="duplicate",
        new="single",
    )
    assert ambiguous["status"] == "error"
    assert ambiguous["matches"] == 2
    assert parse(note_path).body.count("duplicate") == 2


def test_patch_note_appends_to_sections_upserts_sections_and_updates_frontmatter(
    tmp_vault, monkeypatch
) -> None:
    """patch_note covers common safe edit operations without full-body replacement."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    from pkm.tools.notes import patch_note

    note_path = tmp_vault.notes_dir / "section-note.md"
    _write_note(
        note_path,
        note_id="section-note",
        title="Section Note",
        tags=["original"],
        body="Intro\n\n## Findings\n\n- old finding\n\n## Next\n\n- keep next\n",
    )

    appended = _call_tool(
        patch_note,
        note_id="section-note",
        operation="append",
        section="Findings",
        new="- new finding",
    )
    assert appended["status"] == "patched"
    body = parse(note_path).body
    assert body.index("- old finding") < body.index("- new finding") < body.index("## Next")

    upserted = _call_tool(
        patch_note,
        note_id="section-note",
        operation="upsert_section",
        section="Findings",
        new="- replacement finding",
    )
    assert upserted["status"] == "patched"
    body = parse(note_path).body
    assert "- replacement finding" in body
    assert "- old finding" not in body
    assert "## Next\n\n- keep next" in body

    created = _call_tool(
        patch_note,
        note_id="section-note",
        operation="upsert_section",
        section="Decision",
        new="Ship the single patch_note tool.",
    )
    assert created["status"] == "patched"
    body = parse(note_path).body
    assert "## Decision\n\nShip the single patch_note tool." in body

    fm = _call_tool(
        patch_note,
        note_id="section-note",
        operation="frontmatter",
        fields={"tags": ["patched"], "importance": 8},
    )
    assert fm["status"] == "patched"
    note = parse(note_path)
    assert note.meta["tags"] == ["patched"]
    assert note.meta["importance"] == 8
    assert "Ship the single patch_note tool." in note.body


def test_patch_note_handles_daily_notes_prepend_and_stale_hash(tmp_vault, monkeypatch):
    """patch_note searches daily notes and can reject stale writes via base_hash."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    import hashlib
    from pkm.frontmatter import render
    from pkm.tools.notes import patch_note

    current_note = parse(tmp_vault.daily_dir / "2026-04-01.md")
    current_hash = hashlib.sha256(
        render(current_note.meta, current_note.body).encode("utf-8")
    ).hexdigest()
    stale_hash = "not-the-current-hash"

    stale = _call_tool(
        patch_note,
        note_id="2026-04-01",
        operation="prepend",
        new="Daily summary line",
        base_hash=stale_hash,
    )
    assert stale["status"] == "error"
    assert "stale" in stale["summary"].lower()

    patched = _call_tool(
        patch_note,
        note_id="2026-04-01",
        operation="prepend",
        new="Daily summary line",
        base_hash=current_hash,
    )
    assert patched["status"] == "patched"
    assert parse(tmp_vault.daily_dir / "2026-04-01.md").body.startswith(
        "Daily summary line"
    )


def test_read_note_returns_daily_note_with_string_id_and_content_hash(
    tmp_vault, monkeypatch
) -> None:
    """read_note supports daily notes whose YAML id parses as a date."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    from pkm.tools.notes import read_note

    result = _call_tool(read_note, note_id="2026-04-01")

    assert result["note_id"] == "2026-04-01"
    assert isinstance(result["content_hash"], str)
    assert len(result["content_hash"]) == 64


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
