"""Tests for tools/links.py — find_backlinks_for_note."""

from __future__ import annotations

import asyncio
import json

import networkx as nx

from pkm.tools.links import add_wikilink, find_backlinks_for_note, get_note_neighbors


def _run(coro):
    """Run an async tool coroutine synchronously."""
    return asyncio.run(coro)


def test_finds_backlinks_to_mvcc(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(find_backlinks_for_note(note_id="2026-04-01-mvcc")))
    note_ids = [b["note_id"] for b in result["backlinks"]]
    # database-isolation.md and concurrency-note.md both link to 2026-04-01-mvcc
    assert "database-isolation" in note_ids or "concurrency-note" in note_ids
    assert result["count"] >= 1


def test_orphan_has_no_backlinks(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(find_backlinks_for_note(note_id="isolated-note")))
    assert result["count"] == 0
    assert result["backlinks"] == []


def test_unknown_note_returns_empty(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(find_backlinks_for_note(note_id="nonexistent-note-xyz")))
    assert result["count"] == 0
    assert result["note_id"] == "nonexistent-note-xyz"


def test_backlinks_have_required_fields(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(find_backlinks_for_note(note_id="2026-04-01-mvcc")))
    for b in result["backlinks"]:
        assert "title" in b
        assert "path" in b
        assert "note_id" in b


def test_find_backlinks_uses_filename_when_backlink_parse_fails(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    broken = tmp_vault.notes_dir / "broken-backlink.md"
    broken.write_text("---\n: bad: yaml\n---\n", encoding="utf-8")
    monkeypatch.setattr("pkm.wikilinks.find_backlinks", lambda vault, note_id: [broken])
    monkeypatch.setattr(
        "pkm.frontmatter.parse",
        lambda path: (_ for _ in ()).throw(RuntimeError("bad note")),
    )

    result = json.loads(_run(find_backlinks_for_note(note_id="target")))
    assert result["backlinks"] == [
        {
            "title": "broken-backlink",
            "path": "broken-backlink.md",
            "note_id": "broken-backlink",
        }
    ]


def test_add_wikilink_appends_or_inserts_related_section(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    source = tmp_vault.notes_dir / "source-note.md"
    source.write_text(
        "---\nid: source-note\n---\nBody without newline", encoding="utf-8"
    )

    created = _run(
        add_wikilink(
            source_note_id="source-note",
            target_note_id="target-note",
            description="shares test context",
        )
    )
    assert "Added [[target-note]]" in created
    text = source.read_text(encoding="utf-8")
    assert "## Related" in text
    assert "- [[target-note|shares test context]]" in text

    inserted = _run(
        add_wikilink(
            source_note_id="source-note",
            target_note_id="second-note",
            description="same workflow",
        )
    )
    assert "Added [[second-note]]" in inserted
    assert (
        source.read_text(encoding="utf-8")
        .split("## Related", 1)[1]
        .lstrip("\n")
        .startswith("- [[second-note|same workflow]]")
    )


def test_add_wikilink_reports_missing_source_and_write_errors(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    missing = _run(
        add_wikilink(
            source_note_id="missing-note", target_note_id="target", description="why"
        )
    )
    assert "source note 'missing-note' not found" in missing

    source = tmp_vault.notes_dir / "locked-source.md"
    source.write_text("---\nid: locked-source\n---\nBody\n", encoding="utf-8")
    monkeypatch.setattr(
        "pathlib.Path.write_text",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("locked")),
    )
    error = _run(
        add_wikilink(
            source_note_id="locked-source", target_note_id="target", description="why"
        )
    )
    assert error == "Error: locked"


def test_get_note_neighbors_reports_missing_graph_and_semantic_neighbors(
    tmp_vault, monkeypatch
):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    missing = json.loads(_run(get_note_neighbors(note_id="a")))
    assert "graph not found" in missing["error"]

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

    result = json.loads(_run(get_note_neighbors(note_id="a", include_semantic=True)))
    assert result["outbound"][0]["note_id"] == "b"
    assert result["inbound"][0]["note_id"] == "c"
    assert result["semantic"] == [
        {
            "note_id": "semantic",
            "title": "Semantic Neighbor",
            "type": "note",
            "confidence": 0.82,
        }
    ]


def test_get_note_neighbors_reports_unexpected_errors(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    (tmp_vault.pkm_dir / "graph.json").write_text("{bad json", encoding="utf-8")

    result = json.loads(_run(get_note_neighbors(note_id="a")))
    assert "error" in result
