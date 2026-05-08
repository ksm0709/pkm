"""Scenario tests for tiny-agent search and graph discovery tools."""

from __future__ import annotations

import asyncio
import inspect
import json
from types import SimpleNamespace
from unittest.mock import patch

import networkx as nx


def _call_tool(fn, **kwargs):
    result = fn(**kwargs)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
    if isinstance(result, str):
        try:
            return json.loads(result)
        except (TypeError, ValueError):
            return result
    return result


def _write_enriched(vault, clusters) -> None:
    payload = {
        "directed": True,
        "multigraph": False,
        "graph": {},
        "nodes": [],
        "links": [],
        "clusters": clusters,
    }
    vault.graph_enriched_path.write_text(json.dumps(payload), encoding="utf-8")


def test_semantic_search_formats_daemon_results_and_forwards_filters(
    tmp_vault, monkeypatch
) -> None:
    """semantic_search prefers daemon results and formats title, score, description."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result_item = SimpleNamespace(
        title="Ranked Note",
        score=0.87654,
        description="Daemon supplied description",
        path=str(tmp_vault.notes_dir / "missing.md"),
    )

    from pkm.tools import search as search_tools

    with (
        patch.object(
            search_tools, "search_via_daemon", return_value=[result_item]
        ) as daemon,
        patch.object(search_tools, "load_index") as load_index,
    ):
        result = _call_tool(
            search_tools.semantic_search,
            query="ranking",
            top=3,
            memory_type="semantic",
            min_importance=6.5,
        )

    daemon.assert_called_once()
    assert daemon.call_args.args[0] == "ranking"
    assert daemon.call_args.args[1].path == tmp_vault.path
    assert daemon.call_args.kwargs == {
        "top_n": 3,
        "min_importance": 6.5,
        "memory_type_filter": "semantic",
    }
    load_index.assert_not_called()
    assert "Title: Ranked Note" in result
    assert "Score: 0.8765" in result
    assert "Description: Daemon supplied description" in result


def test_semantic_search_falls_back_to_index_and_reads_note_description(
    tmp_vault, monkeypatch
) -> None:
    """Daemon unavailability falls back to local index and fills missing description."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    note_path = tmp_vault.notes_dir / "fallback.md"
    note_path.write_text(
        "---\nid: fallback\ndescription: Frontmatter summary\ntags: []\n---\n\nBody\n",
        encoding="utf-8",
    )
    result_item = SimpleNamespace(
        title="Fallback Note",
        score=0.5,
        description="",
        path=str(note_path),
    )

    from pkm.tools import search as search_tools

    vector_index = object()
    with (
        patch.object(search_tools, "search_via_daemon", return_value=None),
        patch.object(search_tools, "load_index", return_value=vector_index) as load,
        patch.object(search_tools, "search_fn", return_value=[result_item]) as search,
    ):
        result = _call_tool(search_tools.semantic_search, query="fallback", top=2)

    load.assert_called_once()
    assert load.call_args.args[0].path == tmp_vault.path
    search.assert_called_once_with(
        "fallback",
        vector_index,
        top_n=2,
        memory_type_filter=None,
        min_importance=1.0,
    )
    assert "Description: Frontmatter summary" in result


def test_semantic_search_distinguishes_empty_daemon_from_unavailable_daemon(
    tmp_vault, monkeypatch
) -> None:
    """An empty daemon result is final and does not trigger local index fallback."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    from pkm.tools import search as search_tools

    with (
        patch.object(search_tools, "search_via_daemon", return_value=[]),
        patch.object(search_tools, "load_index") as load_index,
    ):
        result = _call_tool(search_tools.semantic_search, query="empty")

    assert result == "No results found."
    load_index.assert_not_called()


def test_semantic_search_reports_downstream_errors(tmp_vault, monkeypatch) -> None:
    """semantic_search converts daemon/index exceptions into user-facing strings."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    from pkm.tools import search as search_tools

    with patch.object(
        search_tools, "search_via_daemon", side_effect=RuntimeError("daemon broke")
    ):
        result = _call_tool(search_tools.semantic_search, query="boom")

    assert result == "Error performing semantic search: daemon broke"


def test_find_surprising_connections_formats_results_empty_and_errors(
    tmp_vault, monkeypatch
) -> None:
    """Surprising-connection wrapper formats bridge metrics and degrades cleanly."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    bridges = [
        {
            "title": "Bridge A",
            "cluster_a": 1,
            "cluster_b": 2,
            "bridge_score": 0.9876,
            "dist_a": 0.123,
            "dist_b": 0.456,
        }
    ]

    from pkm.tools.search import find_surprising_connections

    with patch("pkm.graph.find_surprising_connections", return_value=bridges) as find:
        result = _call_tool(find_surprising_connections, top_n=4)

    find.assert_called_once()
    assert find.call_args.args[0].path == tmp_vault.path
    assert find.call_args.kwargs == {"top_n": 4}
    assert (
        result
        == "[[Bridge A]] bridges cluster 1↔2 (score=0.988, dist_a=0.12, dist_b=0.46)"
    )

    with patch("pkm.graph.find_surprising_connections", return_value=[]):
        empty = _call_tool(find_surprising_connections)
    assert "No surprising connections found" in empty

    with patch(
        "pkm.graph.find_surprising_connections",
        side_effect=RuntimeError("graph unavailable"),
    ):
        error = _call_tool(find_surprising_connections)
    assert error == "Error finding surprising connections: graph unavailable"


def test_list_clusters_reports_minimal_cluster_metadata_and_degradation(
    tmp_vault, monkeypatch
) -> None:
    """list_clusters reads enriched graph metadata without requiring embeddings."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    from pkm.tools.search import list_clusters

    missing = _call_tool(list_clusters)
    assert missing == "No enriched graph found (run `pkm index` first)."

    _write_enriched(tmp_vault, [])
    assert _call_tool(list_clusters) == "No clusters found in enriched graph."

    _write_enriched(
        tmp_vault,
        [
            {
                "id": 7,
                "members": ["b", "a"],
                "top_tags": ["ai", "ops"],
                "centroid_drift": 0.25,
                "is_new": True,
                "centroid": [1.0, 0.0],
            }
        ],
    )

    result = _call_tool(list_clusters)

    assert result == {
        "clusters": [
            {
                "id": 7,
                "member_count": 2,
                "top_tags": ["ai", "ops"],
                "hub_note": None,
                "centroid_drift": 0.25,
                "is_new": True,
            }
        ]
    }

    tmp_vault.graph_enriched_path.write_text("{bad json", encoding="utf-8")
    error = _call_tool(list_clusters)
    assert error.startswith("Error listing clusters:")


def test_list_god_nodes_scores_only_note_nodes_and_handles_gaps(
    tmp_vault, monkeypatch
) -> None:
    """list_god_nodes formats note titles, excludes tag nodes, and handles graph gaps."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    from pkm.tools.search import list_god_nodes

    assert _call_tool(list_god_nodes) == "No graph found (run `pkm index` first)."

    tag_only = nx.DiGraph()
    tag_only.add_node("tag:ai", type="tag", title="ai")
    (tmp_vault.pkm_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(tag_only)), encoding="utf-8"
    )
    assert _call_tool(list_god_nodes) == "No note nodes found in graph."

    graph = nx.DiGraph()
    graph.add_node("a", type="note", title="Alpha")
    graph.add_node("b", type="note", title="Beta")
    graph.add_node("c", type="note", title="Gamma")
    graph.add_node("tag:ai", type="tag", title="AI Tag")
    graph.add_edge("a", "b")
    graph.add_edge("b", "c")
    graph.add_edge("tag:ai", "b")
    (tmp_vault.pkm_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(graph)), encoding="utf-8"
    )

    output = _call_tool(list_god_nodes, top_n=2)

    assert "note_id" in output
    assert "centrality" in output
    assert "Beta" in output
    assert "AI Tag" not in output
    assert sum(title in output for title in ("Alpha", "Beta", "Gamma")) == 2

    (tmp_vault.pkm_dir / "graph_enriched.json").write_text(
        "{bad json", encoding="utf-8"
    )
    error = _call_tool(list_god_nodes)
    assert error.startswith("Error listing god nodes:")


def test_create_hub_note_writes_index_note_and_handles_missing_cases(
    tmp_vault, monkeypatch
) -> None:
    """create_hub_note writes sorted members, resolves filename conflicts, and degrades."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    from pkm.tools.search import create_hub_note

    missing_graph = _call_tool(
        create_hub_note,
        cluster_index=1,
        title="Ops Hub",
        description="Operational notes.",
    )
    assert missing_graph == "No enriched graph found (run `pkm index` first)."

    _write_enriched(
        tmp_vault,
        [
            {
                "id": 1,
                "members": ["zeta-note", "alpha-note"],
                "top_tags": ["ops", "ai"],
            }
        ],
    )

    missing_cluster = _call_tool(
        create_hub_note,
        cluster_index=99,
        title="Ops Hub",
        description="Operational notes.",
    )
    assert "Cluster 99 not found" in missing_cluster

    created = _call_tool(
        create_hub_note,
        cluster_index=1,
        title="Ops Hub!",
        description="Operational notes.",
    )
    assert "Created hub note 'Ops Hub!'" in created
    first_path = tmp_vault.notes_dir / "ops-hub.md"
    assert first_path.exists()
    text = first_path.read_text(encoding="utf-8")
    assert "title: Ops Hub!" in text
    assert "type: index" in text
    assert "importance: 6" in text
    assert "  - ops" in text
    assert "Operational notes." in text
    assert text.index("- [[alpha-note]]") < text.index("- [[zeta-note]]")

    second = _call_tool(
        create_hub_note,
        cluster_index=1,
        title="Ops Hub!",
        description="Second copy.",
    )
    assert "ops-hub-2.md" in second
    assert (tmp_vault.notes_dir / "ops-hub-2.md").exists()

    tmp_vault.graph_enriched_path.write_text("{bad json", encoding="utf-8")
    error = _call_tool(
        create_hub_note,
        cluster_index=1,
        title="Ops Hub",
        description="Operational notes.",
    )
    assert error.startswith("Error creating hub note:")
