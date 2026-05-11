"""Unit tests for wikilinks module."""

from __future__ import annotations


from pkm.config import VaultConfig
from pkm.wikilinks import (
    count_backlinks,
    extract_links,
    find_orphans,
    rewrite_wikilink_targets,
    rewrite_wikilinks_in_vault,
    resolve_link,
)


def test_extract_simple_link():
    assert extract_links("See [[note]] for details.") == ["note"]


def test_extract_aliased_link():
    assert extract_links("See [[note|alias]] for details.") == ["note"]


def test_extract_link_target_with_literal_brackets():
    assert extract_links("See [[[주식분석]xxx]] for details.") == ["[주식분석]xxx"]


def test_extract_aliased_link_with_literal_brackets():
    assert extract_links("See [[[주식분석]xxx|alias [ok]]]") == ["[주식분석]xxx"]


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


def test_count_backlinks_to_note_with_literal_brackets(tmp_vault: VaultConfig):
    target = tmp_vault.notes_dir / "[주식분석]xxx.md"
    target.write_text("---\nid: [주식분석]xxx\ntags: []\n---\n", encoding="utf-8")
    linker = tmp_vault.notes_dir / "bracket-linker.md"
    linker.write_text("Related: [[[주식분석]xxx]]\n", encoding="utf-8")

    counts = count_backlinks(tmp_vault)

    assert counts["[주식분석]xxx"] == 1


def test_find_orphans(tmp_vault: VaultConfig):
    orphans = find_orphans(tmp_vault)
    orphan_names = {p.name for p in orphans}
    # Both notes with no in/out links are orphans
    assert "isolated-note.md" in orphan_names
    assert "untagged-note.md" in orphan_names
    # Connected notes are NOT orphans
    assert "2026-04-01-mvcc.md" not in orphan_names
    assert "database-isolation.md" not in orphan_names


def test_rewrite_wikilink_targets_preserves_alias_and_skips_code_blocks():
    text = (
        "See [[old-note]] and [[old-note|Old Alias]] and [[old-note.md|With ext]].\n"
        "```\n[[old-note]]\n```\n"
        "Embed ![[old-note]] stays unchanged.\n"
    )

    rewritten, count = rewrite_wikilink_targets(text, "old-note", "new-note")

    assert count == 3
    assert "[[new-note]]" in rewritten
    assert "[[new-note|Old Alias]]" in rewritten
    assert "[[new-note|With ext]]" in rewritten
    assert "```\n[[old-note]]\n```" in rewritten
    assert "![[old-note]]" in rewritten


def test_rewrite_wikilink_target_with_literal_brackets():
    text = "See [[[주식분석]xxx]] and [[[주식분석]xxx|old alias]]."

    rewritten, count = rewrite_wikilink_targets(
        text, "[주식분석]xxx", "[주식분석]yyy"
    )

    assert count == 2
    assert "[[[주식분석]yyy]]" in rewritten
    assert "[[[주식분석]yyy|old alias]]" in rewritten


def test_rewrite_wikilinks_in_vault_updates_notes_and_daily(tmp_vault: VaultConfig):
    notes_linker = tmp_vault.notes_dir / "linker.md"
    daily_linker = tmp_vault.daily_dir / "2026-05-04.md"
    notes_linker.write_text("A [[old-note|alias]] link.", encoding="utf-8")
    daily_linker.write_text("Daily [[old-note]] link.", encoding="utf-8")

    result = rewrite_wikilinks_in_vault(tmp_vault, "old-note", "new-note")

    assert result.changed_files == 2
    assert result.replacements == 2
    assert "[[new-note|alias]]" in notes_linker.read_text(encoding="utf-8")
    assert "[[new-note]]" in daily_linker.read_text(encoding="utf-8")
