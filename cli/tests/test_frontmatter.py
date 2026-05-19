"""Tests for markdown frontmatter parsing."""

from __future__ import annotations

from pkm.frontmatter import normalize_frontmatter_text, parse


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


def test_parse_repairs_unquoted_colon_in_title(tmp_path) -> None:
    """A colon-space inside an unquoted title should not block note reads."""
    note_path = tmp_path / "adhd와-생각-집중실행-패턴-허브.md"
    note_path.write_text(
        "---\n"
        "id: adhd와-생각-집중실행-패턴-허브\n"
        "title: ADHD: 생각 집중실행 패턴 허브\n"
        "tags: [hub]\n"
        "---\n\n"
        "# Hub\n"
        "\n"
        "Actual content.\n",
        encoding="utf-8",
    )

    note = parse(note_path)

    assert note.id == "adhd와-생각-집중실행-패턴-허브"
    assert note.title == "ADHD: 생각 집중실행 패턴 허브"
    assert note.body.startswith("# Hub")


def test_normalize_frontmatter_text_quotes_unquoted_colon_title() -> None:
    text = (
        "---\n"
        "id: neo-mcp-opencode-오픈소스-에이전트-허브\n"
        "title: Neo MCP: opencode 오픈소스 에이전트 허브\n"
        "---\n\n"
        "Body\n"
    )

    repaired, changed = normalize_frontmatter_text(text)

    assert changed is True
    assert 'title: "Neo MCP: opencode 오픈소스 에이전트 허브"' in repaired
