"""Tests for related_notes field in pkm search JSON output."""

import json
from click.testing import CliRunner
from pkm.commands.search import search_cmd


def _make_vault(tmp_path):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / "notes").mkdir()
    pkm_dir = vault_dir / ".pkm"
    pkm_dir.mkdir()
    return vault_dir, pkm_dir


def _make_graph(pkm_dir, nodes, edges):
    import networkx as nx

    G = nx.DiGraph()
    for n, attrs in nodes.items():
        G.add_node(n, **attrs)
    for src, tgt, attrs in edges:
        G.add_edge(src, tgt, **attrs)
    (pkm_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(G)), encoding="utf-8"
    )


def test_search_result_has_related_notes_field(tmp_path, monkeypatch):
    """search JSON output includes related_notes with outbound/inbound/semantic keys."""
    vault_dir, pkm_dir = _make_vault(tmp_path)
    _make_graph(
        pkm_dir,
        nodes={"note-a": {"title": "Note A"}, "note-b": {"title": "Note B"}},
        edges=[("note-a", "note-b", {"type": "wikilink"})],
    )

    from pkm.config import VaultConfig

    vault = VaultConfig(name="test", path=vault_dir)

    from pkm.search_engine import SearchResult

    results = [
        SearchResult(
            note_id="note-a",
            title="Note A",
            score=0.9,
            rank=1,
            tags=[],
            backlink_count=0,
        )
    ]

    from pkm.commands.search import format_search_results
    from rich.console import Console
    from io import StringIO
    import sys

    captured = StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    format_search_results(
        query="test",
        results=results,
        output_format="json",
        console=Console(),
        vault=vault,
    )
    output = json.loads(captured.getvalue())

    assert "results" in output
    r = output["results"][0]
    assert "related_notes" in r
    assert "outbound" in r["related_notes"]
    assert "inbound" in r["related_notes"]
    assert "semantic" in r["related_notes"]
    assert any(n["note_id"] == "note-b" for n in r["related_notes"]["outbound"])


def test_search_result_no_graph_context_key(tmp_path, monkeypatch):
    """related_notes replaces graph_context — old key must not appear."""
    vault_dir, pkm_dir = _make_vault(tmp_path)
    _make_graph(pkm_dir, nodes={"note-a": {"title": "Note A"}}, edges=[])

    from pkm.config import VaultConfig

    vault = VaultConfig(name="test", path=vault_dir)

    from pkm.search_engine import SearchResult

    results = [
        SearchResult(
            note_id="note-a",
            title="Note A",
            score=0.9,
            rank=1,
            tags=[],
            backlink_count=0,
        )
    ]

    from pkm.commands.search import format_search_results
    from rich.console import Console
    from io import StringIO
    import sys

    captured = StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    format_search_results(
        query="test",
        results=results,
        output_format="json",
        console=Console(),
        vault=vault,
    )
    output = json.loads(captured.getvalue())
    r = output["results"][0]
    assert "graph_context" not in r


def test_search_no_depth_option(tmp_path):
    """--depth option must not exist on search command."""
    runner = CliRunner()
    result = runner.invoke(search_cmd, ["--help"])
    assert "--depth" not in result.output


def test_mcp_search_has_related_notes(tmp_path, monkeypatch):
    """MCP search tool includes related_notes in each result."""
    vault_dir, pkm_dir = _make_vault(tmp_path)
    _make_graph(
        pkm_dir,
        nodes={"note-a": {"title": "Note A"}, "note-b": {"title": "Note B"}},
        edges=[("note-a", "note-b", {"type": "wikilink"})],
    )

    from pkm.config import VaultConfig

    vault = VaultConfig(name="test", path=vault_dir)

    from pkm.search_engine import SearchResult

    mock_results = [
        SearchResult(
            note_id="note-a",
            title="Note A",
            score=0.9,
            rank=1,
            tags=[],
            backlink_count=0,
        )
    ]

    import pkm.mcp_server as mcp_mod

    monkeypatch.setattr(mcp_mod, "_get_vault", lambda v=None: vault)

    from pkm import search_engine

    monkeypatch.setattr(
        search_engine, "search_via_daemon", lambda *a, **kw: mock_results
    )

    result = mcp_mod.search(query="test")
    assert "results" in result
    r = result["results"][0]
    assert "related_notes" in r
    assert "outbound" in r["related_notes"]
