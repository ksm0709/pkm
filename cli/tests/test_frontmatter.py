"""Tests for markdown frontmatter parsing."""

from __future__ import annotations

from pkm.frontmatter import parse


def test_parse_strips_consecutive_frontmatter_blocks_from_body(tmp_path) -> None:
    """Notes created with duplicated leading metadata must not render metadata as body."""
    note_path = tmp_path / "double-frontmatter.md"
    note_path.write_text(
        "---\n"
        "id: outer-note\n"
        "memory_type: semantic\n"
        "tags: pkm-webapp, logging\n"
        "---\n"
        "\n"
        "---\n"
        "id: inner-note\n"
        "aliases: [logger]\n"
        "tags: [pkm-webapp, logging]\n"
        "---\n"
        "\n"
        "# Logger\n"
        "\n"
        "Actual content.\n",
        encoding="utf-8",
    )

    note = parse(note_path)

    assert note.id == "outer-note"
    assert "memory_type" in note.meta
    assert note.body.startswith("# Logger")
    assert "aliases: [logger]" not in note.body
