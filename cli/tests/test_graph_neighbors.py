"""Tests for get_note_neighbors in pkm.tools.links and pkm graph neighbors CLI."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import networkx as nx
import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vault(tmp_path: Path) -> VaultConfig:
    vault_path = tmp_path / "vault"
    for d in ("notes", "daily", "tags", ".pkm"):
        (vault_path / d).mkdir(parents=True)
    return VaultConfig(name="vault", path=vault_path)


def _write_graph(pkm_dir: Path, G: nx.DiGraph) -> None:
    data = nx.node_link_data(G)
    (pkm_dir / "graph.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def _write_enriched(pkm_dir: Path, G: nx.DiGraph) -> None:
    data = nx.node_link_data(G)
    data["graph_tier"] = "enriched"
    data["schema_version"] = 1
    data["clusters"] = []
    (pkm_dir / "graph_enriched.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def _make_base_graph() -> nx.DiGraph:
    """Build a small test graph:
    note-a --wikilink--> note-b
    note-a --wikilink--> ghost-note  (note_or_unresolved)
    note-a --has_tag--> tag:science  (tag node)
    note-c --wikilink--> note-a      (inbound for note-a)
    """
    G = nx.DiGraph()
    G.add_node("note-a", type="note", title="Note A")
    G.add_node("note-b", type="note", title="Note B")
    G.add_node("note-c", type="note", title="Note C")
    G.add_node("ghost-note", type="note_or_unresolved", title="ghost-note")
    G.add_node("tag:science", type="tag", name="science")

    G.add_edge("note-a", "note-b", type="wikilink")
    G.add_edge("note-a", "ghost-note", type="wikilink")
    G.add_edge("note-a", "tag:science", type="has_tag")
    G.add_edge("note-c", "note-a", type="wikilink")
    return G


# ---------------------------------------------------------------------------
# tools/links.py unit tests
# ---------------------------------------------------------------------------


def test_get_note_neighbors_outbound(tmp_path, monkeypatch):
    """outbound list contains wikilink target note."""
    vault = _make_vault(tmp_path)
    _write_graph(vault.pkm_dir, _make_base_graph())
    monkeypatch.setenv("PKM_VAULT_DIR", str(vault.path))

    from pkm.tools.links import get_note_neighbors

    result = json.loads(asyncio.run(get_note_neighbors(note_id="note-a")))
    outbound_ids = [x["note_id"] for x in result["outbound"]]
    assert "note-b" in outbound_ids


def test_get_note_neighbors_inbound(tmp_path, monkeypatch):
    """inbound list contains note that links to target."""
    vault = _make_vault(tmp_path)
    _write_graph(vault.pkm_dir, _make_base_graph())
    monkeypatch.setenv("PKM_VAULT_DIR", str(vault.path))

    from pkm.tools.links import get_note_neighbors

    result = json.loads(asyncio.run(get_note_neighbors(note_id="note-a")))
    inbound_ids = [x["note_id"] for x in result["inbound"]]
    assert "note-c" in inbound_ids


def test_get_note_neighbors_tag(tmp_path, monkeypatch):
    """tag nodes appear in outbound with type='tag'."""
    vault = _make_vault(tmp_path)
    _write_graph(vault.pkm_dir, _make_base_graph())
    monkeypatch.setenv("PKM_VAULT_DIR", str(vault.path))

    from pkm.tools.links import get_note_neighbors

    result = json.loads(asyncio.run(get_note_neighbors(note_id="note-a")))
    tag_items = [x for x in result["outbound"] if x["type"] == "tag"]
    assert len(tag_items) == 1
    assert tag_items[0]["note_id"] == "tag:science"


def test_get_note_neighbors_ghost(tmp_path, monkeypatch):
    """note_or_unresolved nodes appear in outbound."""
    vault = _make_vault(tmp_path)
    _write_graph(vault.pkm_dir, _make_base_graph())
    monkeypatch.setenv("PKM_VAULT_DIR", str(vault.path))

    from pkm.tools.links import get_note_neighbors

    result = json.loads(asyncio.run(get_note_neighbors(note_id="note-a")))
    ghost_items = [x for x in result["outbound"] if x["type"] == "note_or_unresolved"]
    assert len(ghost_items) == 1
    assert ghost_items[0]["note_id"] == "ghost-note"


def test_get_note_neighbors_no_graph(tmp_path, monkeypatch):
    """Returns error message when graph.json is missing."""
    vault = _make_vault(tmp_path)
    monkeypatch.setenv("PKM_VAULT_DIR", str(vault.path))

    from pkm.tools.links import get_note_neighbors

    result = json.loads(asyncio.run(get_note_neighbors(note_id="note-a")))
    assert "error" in result
    assert "pkm index" in result["error"]


def test_get_note_neighbors_unknown_note(tmp_path, monkeypatch):
    """Note not in graph returns empty lists, not an error."""
    vault = _make_vault(tmp_path)
    _write_graph(vault.pkm_dir, _make_base_graph())
    monkeypatch.setenv("PKM_VAULT_DIR", str(vault.path))

    from pkm.tools.links import get_note_neighbors

    result = json.loads(asyncio.run(get_note_neighbors(note_id="does-not-exist")))
    assert "error" not in result
    assert result["outbound"] == []
    assert result["inbound"] == []
    assert result["semantic"] == []


def test_get_note_neighbors_semantic_dedup(tmp_path, monkeypatch):
    """Bidirectional semantic edges appear only once in results."""
    vault = _make_vault(tmp_path)
    base_G = _make_base_graph()
    _write_graph(vault.pkm_dir, base_G)

    enriched_G = base_G.copy()
    # Both directions of the same semantic connection
    enriched_G.add_edge("note-a", "note-b", type="semantic_similar", confidence=0.85)
    enriched_G.add_edge("note-b", "note-a", type="semantic_similar", confidence=0.85)
    _write_enriched(vault.pkm_dir, enriched_G)
    monkeypatch.setenv("PKM_VAULT_DIR", str(vault.path))

    from pkm.tools.links import get_note_neighbors

    result = json.loads(
        asyncio.run(get_note_neighbors(note_id="note-a", include_semantic=True))
    )
    sem_ids = [x["note_id"] for x in result["semantic"]]
    assert sem_ids.count("note-b") == 1


def test_get_note_neighbors_semantic(tmp_path, monkeypatch):
    """semantic list populated when include_semantic=True and enriched graph exists."""
    vault = _make_vault(tmp_path)
    base_G = _make_base_graph()
    _write_graph(vault.pkm_dir, base_G)

    enriched_G = base_G.copy()
    enriched_G.add_edge("note-a", "note-b", type="semantic_similar", confidence=0.85)
    _write_enriched(vault.pkm_dir, enriched_G)
    monkeypatch.setenv("PKM_VAULT_DIR", str(vault.path))

    from pkm.tools.links import get_note_neighbors

    result = json.loads(
        asyncio.run(get_note_neighbors(note_id="note-a", include_semantic=True))
    )
    assert len(result["semantic"]) >= 1
    sem_ids = [x["note_id"] for x in result["semantic"]]
    assert "note-b" in sem_ids
    assert all("confidence" in x for x in result["semantic"])


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    return CliRunner()


def _cli_invoke(runner, tmp_vault, monkeypatch, *args):
    monkeypatch.setattr(
        "pkm.config.discover_vaults",
        lambda root=None: {"test-vault": tmp_vault},
    )
    monkeypatch.setattr("pkm.config.load_config", lambda: {})
    return runner.invoke(main, list(args), catch_exceptions=False)


def test_cli_neighbors_json(tmp_path, runner, monkeypatch):
    """CLI json output is parseable and has correct structure."""
    vault = _make_vault(tmp_path)
    _write_graph(vault.pkm_dir, _make_base_graph())

    result = _cli_invoke(runner, vault, monkeypatch, "graph", "neighbors", "note-a")
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["note_id"] == "note-a"
    assert "outbound" in data
    assert "inbound" in data
    assert "semantic" in data


def test_cli_neighbors_table(tmp_path, runner, monkeypatch):
    """CLI --format table runs without error."""
    vault = _make_vault(tmp_path)
    _write_graph(vault.pkm_dir, _make_base_graph())

    result = _cli_invoke(
        runner, vault, monkeypatch, "graph", "neighbors", "note-a", "--format", "table"
    )
    assert result.exit_code == 0


def test_cli_neighbors_no_graph(tmp_path, runner, monkeypatch):
    """CLI exits with non-zero when graph.json missing."""
    vault = _make_vault(tmp_path)

    result = runner.invoke(
        main,
        ["graph", "neighbors", "note-a"],
        obj={"vault": vault},
        catch_exceptions=False,
    )
    assert result.exit_code != 0
