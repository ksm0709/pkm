"""Framework-free domain tests for partial note edits."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pkm.frontmatter import parse, render
from pkm.tools.notes import _patch_note_impl


def _write_note(path: Path, *, note_id: str, title: str, body: str, tags=None) -> None:
    tags = tags or []
    tag_lines = "\n".join(f"  - {tag}" for tag in tags)
    path.write_text(
        f"---\nid: {note_id}\ntitle: {title}\ntags:\n{tag_lines}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_patch_note_rejects_ambiguous_matches(tmp_vault) -> None:
    """Exact replacement refuses to guess when the body fragment is ambiguous."""

    note_path = tmp_vault.notes_dir / "2026-04-01-mvcc.md"
    note_path.write_text(
        note_path.read_text(encoding="utf-8") + "\nduplicate\nduplicate\n",
        encoding="utf-8",
    )
    ambiguous = _patch_note_impl(
        tmp_vault,
        note_id="2026-04-01-mvcc",
        operation="replace",
        old="duplicate",
        new="single",
    )
    assert ambiguous["status"] == "error"
    assert ambiguous["matches"] == 2
    assert parse(note_path).body.count("duplicate") == 2


def test_patch_note_appends_to_sections_upserts_sections_and_updates_frontmatter(
    tmp_vault,
) -> None:
    """patch_note covers common safe edit operations without full-body replacement."""
    note_path = tmp_vault.notes_dir / "section-note.md"
    _write_note(
        note_path,
        note_id="section-note",
        title="Section Note",
        tags=["original"],
        body="Intro\n\n## Findings\n\n- old finding\n\n## Next\n\n- keep next\n",
    )

    appended = _patch_note_impl(
        tmp_vault,
        note_id="section-note",
        operation="append",
        section="Findings",
        new="- new finding",
    )
    assert appended["status"] == "patched"
    body = parse(note_path).body
    assert body.index("- old finding") < body.index("- new finding") < body.index("## Next")

    upserted = _patch_note_impl(
        tmp_vault,
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

    created = _patch_note_impl(
        tmp_vault,
        note_id="section-note",
        operation="upsert_section",
        section="Decision",
        new="Ship the single patch_note tool.",
    )
    assert created["status"] == "patched"
    body = parse(note_path).body
    assert "## Decision\n\nShip the single patch_note tool." in body

    fm = _patch_note_impl(
        tmp_vault,
        note_id="section-note",
        operation="frontmatter",
        fields={"tags": ["patched"], "importance": 8},
    )
    assert fm["status"] == "patched"
    note = parse(note_path)
    assert note.meta["tags"] == ["patched"]
    assert note.meta["importance"] == 8
    assert "Ship the single patch_note tool." in note.body


def test_patch_note_handles_daily_notes_prepend_and_stale_hash(tmp_vault):
    """patch_note searches daily notes and can reject stale writes via base_hash."""
    current_note = parse(tmp_vault.daily_dir / "2026-04-01.md")
    current_hash = hashlib.sha256(
        render(current_note.meta, current_note.body).encode("utf-8")
    ).hexdigest()
    stale_hash = "not-the-current-hash"

    stale = _patch_note_impl(
        tmp_vault,
        note_id="2026-04-01",
        operation="prepend",
        new="Daily summary line",
        base_hash=stale_hash,
    )
    assert stale["status"] == "error"
    assert "stale" in stale["summary"].lower()

    patched = _patch_note_impl(
        tmp_vault,
        note_id="2026-04-01",
        operation="prepend",
        new="Daily summary line",
        base_hash=current_hash,
    )
    assert patched["status"] == "patched"
    assert parse(tmp_vault.daily_dir / "2026-04-01.md").body.startswith(
        "Daily summary line"
    )
