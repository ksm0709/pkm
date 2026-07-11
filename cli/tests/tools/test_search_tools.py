"""Scenario tests for vault-scoped graph discovery domain functions."""

from __future__ import annotations

import json
from unittest.mock import patch

import networkx as nx
import pytest


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


def test_find_surprising_connections_formats_results_empty_and_errors(
    tmp_vault,
) -> None:
    """Surprising connections format bridge metrics and propagate graph errors."""
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
        result = find_surprising_connections(tmp_vault, top_n=4)

    find.assert_called_once_with(tmp_vault, top_n=4)
    assert (
        result
        == "[[Bridge A]] bridges cluster 1↔2 (score=0.988, dist_a=0.12, dist_b=0.46)"
    )

    with patch("pkm.graph.find_surprising_connections", return_value=[]):
        empty = find_surprising_connections(tmp_vault)
    assert "No surprising connections found" in empty

    with patch(
        "pkm.graph.find_surprising_connections",
        side_effect=RuntimeError("graph unavailable"),
    ):
        with pytest.raises(RuntimeError, match="graph unavailable"):
            find_surprising_connections(tmp_vault)


def test_list_clusters_reports_minimal_cluster_metadata_and_degradation(
    tmp_vault,
) -> None:
    """list_clusters reads enriched graph metadata without requiring embeddings."""
    from pkm.tools.search import list_clusters

    missing = list_clusters(tmp_vault)
    assert missing == "No enriched graph found (run `pkm index` first)."

    _write_enriched(tmp_vault, [])
    assert list_clusters(tmp_vault) == "No clusters found in enriched graph."

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

    result = json.loads(list_clusters(tmp_vault))

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
    with pytest.raises(json.JSONDecodeError):
        list_clusters(tmp_vault)


def test_list_god_nodes_scores_only_note_nodes_and_handles_gaps(
    tmp_vault,
) -> None:
    """list_god_nodes formats note titles, excludes tag nodes, and handles graph gaps."""
    from pkm.tools.search import list_god_nodes

    assert list_god_nodes(tmp_vault) == "No graph found (run `pkm index` first)."

    tag_only = nx.DiGraph()
    tag_only.add_node("tag:ai", type="tag", title="ai")
    (tmp_vault.pkm_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(tag_only)), encoding="utf-8"
    )
    assert list_god_nodes(tmp_vault) == "No note nodes found in graph."

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

    output = list_god_nodes(tmp_vault, top_n=2)

    assert "note_id" in output
    assert "centrality" in output
    assert "Beta" in output
    assert "AI Tag" not in output
    assert sum(title in output for title in ("Alpha", "Beta", "Gamma")) == 2

    (tmp_vault.pkm_dir / "graph_enriched.json").write_text(
        "{bad json", encoding="utf-8"
    )
    with pytest.raises(json.JSONDecodeError):
        list_god_nodes(tmp_vault)


def test_create_hub_note_writes_index_note_and_handles_missing_cases(
    tmp_vault,
) -> None:
    """create_hub_note writes sorted members, resolves filename conflicts, and degrades."""
    from pkm.tools.search import create_hub_note

    missing_graph = create_hub_note(
        tmp_vault,
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

    missing_cluster = create_hub_note(
        tmp_vault,
        cluster_index=99,
        title="Ops Hub",
        description="Operational notes.",
    )
    assert "Cluster 99 not found" in missing_cluster

    created = create_hub_note(
        tmp_vault,
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

    second = create_hub_note(
        tmp_vault,
        cluster_index=1,
        title="Ops Hub!",
        description="Second copy.",
    )
    assert "ops-hub-2.md" in second
    assert (tmp_vault.notes_dir / "ops-hub-2.md").exists()

    tmp_vault.graph_enriched_path.write_text("{bad json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        create_hub_note(
            tmp_vault,
            cluster_index=1,
            title="Ops Hub",
            description="Operational notes.",
        )
