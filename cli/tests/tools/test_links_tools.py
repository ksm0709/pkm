"""Tests for framework-free vault-scoped link domain operations."""

from __future__ import annotations

import json

import networkx as nx
import pytest

from pkm.tools.links import _get_note_neighbors_data, add_wikilink


def test_add_wikilink_appends_and_inserts_related_entries(tmp_vault) -> None:
    source = tmp_vault.notes_dir / "source-note.md"
    source.write_text(
        "---\nid: source-note\n---\nBody without newline", encoding="utf-8"
    )

    created = add_wikilink(
        tmp_vault,
        source_note_id="source-note",
        target_note_id="target-note",
        description="shares test context",
    )
    assert "Added [[target-note]]" in created
    text = source.read_text(encoding="utf-8")
    assert "## Related" in text
    assert "- [[target-note|shares test context]]" in text

    inserted = add_wikilink(
        tmp_vault,
        source_note_id="source-note",
        target_note_id="second-note",
        description="same workflow",
    )
    assert "Added [[second-note]]" in inserted
    assert (
        source.read_text(encoding="utf-8")
        .split("## Related", 1)[1]
        .lstrip("\n")
        .startswith("- [[second-note|same workflow]]")
    )


def test_add_wikilink_reports_missing_source(tmp_vault) -> None:
    result = add_wikilink(
        tmp_vault,
        source_note_id="missing-note",
        target_note_id="target",
        description="why",
    )

    assert "source note 'missing-note' not found" in result


def test_add_wikilink_propagates_write_errors(tmp_vault, monkeypatch) -> None:
    source = tmp_vault.notes_dir / "locked-source.md"
    source.write_text("---\nid: locked-source\n---\nBody\n", encoding="utf-8")
    monkeypatch.setattr(
        "pathlib.Path.write_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("locked")),
    )

    with pytest.raises(OSError, match="locked"):
        add_wikilink(
            tmp_vault,
            source_note_id="locked-source",
            target_note_id="target",
            description="why",
        )


def test_get_note_neighbors_requires_graph(tmp_vault) -> None:
    with pytest.raises(FileNotFoundError, match="graph not found"):
        _get_note_neighbors_data(tmp_vault, "a")


def test_get_note_neighbors_returns_structural_and_semantic_neighbors(tmp_vault) -> None:
    graph = nx.DiGraph()
    graph.add_node("a", title="A")
    graph.add_node("b", title="B")
    graph.add_node("c", title="C")
    graph.add_edge("a", "b")
    graph.add_edge("c", "a")
    (tmp_vault.pkm_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(graph)), encoding="utf-8"
    )

    enriched = nx.Graph()
    enriched.add_node("a", title="A")
    enriched.add_node("semantic", title="Semantic Neighbor")
    enriched.add_edge("a", "semantic", type="semantic_similar", confidence=0.82)
    (tmp_vault.pkm_dir / "graph_enriched.json").write_text(
        json.dumps(nx.node_link_data(enriched)), encoding="utf-8"
    )

    result = _get_note_neighbors_data(tmp_vault, "a", include_semantic=True)

    assert result["outbound"] == [{"note_id": "b", "title": "B", "type": "note"}]
    assert result["inbound"] == [{"note_id": "c", "title": "C", "type": "note"}]
    assert result["semantic"] == [
        {
            "note_id": "semantic",
            "title": "Semantic Neighbor",
            "type": "note",
            "confidence": 0.82,
        }
    ]


def test_get_note_neighbors_returns_empty_for_unknown_note(tmp_vault) -> None:
    graph = nx.DiGraph()
    graph.add_node("known", title="Known")
    (tmp_vault.pkm_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(graph)), encoding="utf-8"
    )

    assert _get_note_neighbors_data(tmp_vault, "missing") == {
        "note_id": "missing",
        "outbound": [],
        "inbound": [],
        "semantic": [],
    }
