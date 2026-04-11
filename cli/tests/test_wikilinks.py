"""Unit tests for wikilinks module."""

from __future__ import annotations


from pkm.config import VaultConfig
from pkm.wikilinks import (
    count_backlinks,
    extract_links,
    find_orphans,
    resolve_link,
)


def test_extract_simple_link():
    assert extract_links("See [[note]] for details.") == ["note"]


def test_extract_aliased_link():
    assert extract_links("See [[note|alias]] for details.") == ["note"]


def test_extract_ignores_embeds():
    links = extract_links("Embed: ![[image.png]] and [[real-note]]")
    assert "image.png" not in links
    assert "real-note" in links


def test_extract_ignores_code_blocks():
    text = "Before\n```\n[[inside-code]]\n```\nAfter [[outside]]"
    links = extract_links(text)
    assert "inside-code" not in links
    assert "outside" in links


def test_extract_strips_md_extension():
    assert extract_links("See [[note.md]] for details.") == ["note"]


def test_resolve_link_notes(tmp_vault: VaultConfig):
    result = resolve_link(tmp_vault, "2026-04-01-mvcc")
    assert result is not None
    assert result == tmp_vault.notes_dir / "2026-04-01-mvcc.md"


def test_resolve_link_tasks(tmp_vault: VaultConfig):
    result = resolve_link(tmp_vault, "ongoing")
    assert result is not None
    assert result == tmp_vault.tasks_dir / "ongoing.md"


def test_resolve_link_daily(tmp_vault: VaultConfig):
    result = resolve_link(tmp_vault, "2026-04-01")
    assert result is not None
    assert result == tmp_vault.daily_dir / "2026-04-01.md"


def test_resolve_link_not_found(tmp_vault: VaultConfig):
    result = resolve_link(tmp_vault, "nonexistent-note")
    assert result is None


def test_count_backlinks(tmp_vault: VaultConfig):
    counts = count_backlinks(tmp_vault)
    # 2026-04-01-mvcc is linked from database-isolation.md
    assert counts["2026-04-01-mvcc"] >= 1
    # database-isolation is linked from 2026-04-01-mvcc.md
    assert counts["database-isolation"] >= 1
    # orphan notes have zero backlinks
    assert counts["isolated-note"] == 0
    assert counts["untagged-note"] == 0


def test_find_orphans(tmp_vault: VaultConfig):
    orphans = find_orphans(tmp_vault)
    orphan_names = {p.name for p in orphans}
    # Both notes with no in/out links are orphans
    assert "isolated-note.md" in orphan_names
    assert "untagged-note.md" in orphan_names
    # Connected notes are NOT orphans
    assert "2026-04-01-mvcc.md" not in orphan_names
    assert "database-isolation.md" not in orphan_names
