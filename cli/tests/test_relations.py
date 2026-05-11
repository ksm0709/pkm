"""Tests for graph-native PKM relations."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig
from pkm.graph import build_ast_and_graph


def _write_note(
    directory: Path,
    name: str,
    *,
    note_id: str | None = None,
    body: str,
    extra_frontmatter: str = "",
) -> Path:
    note_id = note_id or name
    frontmatter = f"---\nid: {note_id}\naliases: []\ntags: []\n{extra_frontmatter}---\n\n"
    path = directory / f"{name}.md"
    path.write_text(frontmatter + body, encoding="utf-8")
    return path


@pytest.fixture
def relation_vault(tmp_path: Path) -> VaultConfig:
    vault_path = tmp_path / "relations-vault"
    for directory in ("notes", "daily", "tags", ".pkm"):
        (vault_path / directory).mkdir(parents=True)
    return VaultConfig(name="relations-vault", path=vault_path)


@pytest.fixture
def relation_cli(monkeypatch, relation_vault):
    runner = CliRunner()
    monkeypatch.setattr(
        "pkm.config.discover_vaults",
        lambda *a, **kw: {"relations-vault": relation_vault},
    )
    monkeypatch.setattr("pkm.config.load_config", lambda: {})

    def invoke(*args, catch_exceptions=False):
        return runner.invoke(
            main,
            ["--vault", "relations-vault", *args],
            catch_exceptions=catch_exceptions,
        )

    return invoke


def test_relation_parser_extracts_targets_reasons_aliases_brackets_and_lines():
    from pkm.relations import parse_relation_markers

    body = "\n".join(
        [
            "Intro",
            "&depends_on [[Vector Index|index]] - semantic search needs embeddings",
            "&related [[[주식분석]xxx]]",
            "```",
            "&depends_on [[Ignored]] - inside code",
            "```",
            "&orphan",
        ]
    )

    result = parse_relation_markers(body, source_path="notes/source.md")

    assert [(m.type, m.target, m.reason, m.line) for m in result.markers] == [
        (
            "depends_on",
            "Vector Index",
            "semantic search needs embeddings",
            2,
        ),
        ("related", "[주식분석]xxx", None, 3),
    ]
    assert result.malformed[0]["type"] == "orphan"
    assert result.malformed[0]["line"] == 7


def test_vocabulary_note_parser_accepts_heading_grammar_and_ignores_prose():
    from pkm.relations import parse_vault_vocabulary

    text = """---
id: pkm-relation-vocabulary
type: index
tags: []
---

Human editable guidance stays here.

## depends_on

- Description: A requires B.
- Aliases: requires, needs
- Inverse: enables
- Example: &depends_on [[Vector Index]]
- Unknown: ignored

## Not A Relation!

Ignore this section.
"""

    entries = parse_vault_vocabulary(text)

    assert set(entries) == {"depends_on"}
    assert entries["depends_on"].description == "A requires B."
    assert entries["depends_on"].aliases == ["requires", "needs"]
    assert entries["depends_on"].inverse == "enables"
    assert entries["depends_on"].examples == ["&depends_on [[Vector Index]]"]


def test_build_graph_writes_relation_metadata_vocabulary_and_audit(relation_vault):
    _write_note(
        relation_vault.notes_dir,
        "source",
        note_id="source",
        body="Related: [[target]].\n&depends_on [[target]] - source needs target\n",
    )
    _write_note(
        relation_vault.notes_dir,
        "target",
        note_id="target",
        body="Target note.\n",
    )
    _write_note(
        relation_vault.daily_dir,
        "2026-05-11",
        note_id="2026-05-11",
        body="&depends_on [[source]] - daily observation\n",
    )
    _write_note(
        relation_vault.notes_dir,
        "unknown",
        note_id="unknown",
        body="&implemented_by [[target]]\n",
    )

    build_ast_and_graph(relation_vault)

    graph = nx.node_link_graph(
        json.loads(relation_vault.graph_path.read_text(encoding="utf-8"))
    )
    edge = graph.edges["source", "target"]
    assert edge["type"] == "wikilink"
    assert edge["relations"] == [
        {
            "type": "depends_on",
            "reason": "source needs target",
            "source": {"path": "notes/source.md", "line": 2},
        }
    ]
    assert "relations" not in graph.edges["2026-05-11", "source"]

    vocabulary = json.loads(
        relation_vault.relations_vocabulary_path.read_text(encoding="utf-8")
    )
    assert "depends_on" in vocabulary["built_in"]
    assert vocabulary["observed"]["implemented_by"]["count"] == 1

    audit = json.loads(relation_vault.relations_audit_path.read_text(encoding="utf-8"))
    assert audit["daily_promotion_candidates"][0]["source"]["path"] == (
        "daily/2026-05-11.md"
    )
    assert audit["unknown_relations"][0]["type"] == "implemented_by"
    assert audit["missing_reasons"][0]["type"] == "implemented_by"


def test_relations_cli_rescans_markdown_and_promotes_vocabulary(
    relation_vault, relation_cli
):
    _write_note(
        relation_vault.notes_dir,
        "source",
        note_id="source",
        body="&implemented_by [[target]] - prototype relation\n",
    )
    _write_note(
        relation_vault.notes_dir,
        "target",
        note_id="target",
        body="Target note.\n",
    )

    listed = relation_cli("relations")
    assert listed.exit_code == 0
    payload = json.loads(listed.output)
    assert payload["observed"]["implemented_by"]["count"] == 1
    assert payload["cache_status"] in {"live_scan", "fresh_cache"}

    observed = relation_cli("relations", "observed")
    assert observed.exit_code == 0
    observed_payload = json.loads(observed.output)
    assert observed_payload["relations"][0]["type"] == "implemented_by"

    shown = relation_cli("relations", "show", "implemented_by")
    assert shown.exit_code == 0
    shown_payload = json.loads(shown.output)
    assert shown_payload["relation"]["type"] == "implemented_by"
    assert shown_payload["usage"]["count"] == 1
    assert shown_payload["usage"]["common_targets"] == [{"target": "target", "count": 1}]

    promoted = relation_cli("relations", "promote", "implemented_by")
    assert promoted.exit_code == 0
    vocabulary_note = relation_vault.notes_dir / "pkm-relation-vocabulary.md"
    assert vocabulary_note.exists()
    assert "type: index" in vocabulary_note.read_text(encoding="utf-8")
    assert "## implemented_by" in vocabulary_note.read_text(encoding="utf-8")

    audit = relation_cli("relations", "audit")
    assert audit.exit_code == 0
    audit_payload = json.loads(audit.output)
    assert audit_payload["unknown_relations"] == []
