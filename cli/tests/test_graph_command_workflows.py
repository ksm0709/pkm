"""Scenario tests for graph CLI command output modes."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def graph_cli(tmp_vault: VaultConfig, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("pkm.cli.available_update", lambda _version: None)
    monkeypatch.setattr(
        "pkm.config.discover_vaults",
        lambda root=None: {tmp_vault.name: tmp_vault},
    )
    monkeypatch.setattr("pkm.config.load_config", lambda: {})

    def invoke(*args: str):
        return CliRunner().invoke(
            main,
            ["--vault", tmp_vault.name, *args],
            catch_exceptions=False,
        )

    return invoke


def test_graph_surprising_json_wraps_results_and_passes_top(
    graph_cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    """JSON mode preserves machine-readable results and forwards the requested limit."""
    calls: list[int] = []

    def fake_find(_vault, top_n: int):
        calls.append(top_n)
        return [
            {
                "note_id": "bridge-a",
                "title": "Bridge A",
                "cluster_a": 0,
                "cluster_b": 1,
                "bridge_score": 0.8123,
                "dist_a": 0.11,
                "dist_b": 0.22,
            }
        ]

    monkeypatch.setattr("pkm.graph.find_surprising_connections", fake_find)

    result = graph_cli("graph", "surprising", "--top", "3")

    assert result.exit_code == 0, result.output
    assert calls == [3]
    payload = json.loads(result.output)
    assert payload["results"][0]["title"] == "Bridge A"


def test_graph_surprising_table_renders_bridge_notes(
    graph_cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Table mode gives operators bridge note titles, cluster pairs, and scores."""
    monkeypatch.setattr(
        "pkm.graph.find_surprising_connections",
        lambda _vault, top_n: [
            {
                "note_id": "bridge-a",
                "title": "Bridge A",
                "cluster_a": 0,
                "cluster_b": 1,
                "bridge_score": 0.8123,
                "dist_a": 0.11,
                "dist_b": 0.22,
            },
            {
                "note_id": "bridge-b",
                "title": "Bridge B",
                "cluster_a": 2,
                "cluster_b": 4,
                "bridge_score": 0.4567,
                "dist_a": 0.33,
                "dist_b": 0.44,
            },
        ],
    )

    result = graph_cli("graph", "surprising", "--format", "table")

    assert result.exit_code == 0, result.output
    assert "Top 2 Bridge Notes" in result.output
    assert "Bridge A" in result.output
    assert "Bridge B" in result.output
    assert "0↔1" in result.output
    assert "2↔4" in result.output
    assert "0.812" in result.output
    assert "0.457" in result.output


def test_graph_surprising_table_guides_when_no_results(
    graph_cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty bridge results tell the user to build the enriched graph first."""
    monkeypatch.setattr(
        "pkm.graph.find_surprising_connections", lambda _vault, top_n: []
    )

    result = graph_cli("graph", "surprising", "--format", "table")

    assert result.exit_code == 0, result.output
    assert "No surprising connections found" in result.output
    assert "pkm index" in result.output


def test_graph_neighbors_table_reports_no_connections(
    graph_cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A note with no graph edges reports a clear empty-neighbor state."""
    monkeypatch.setattr(
        "pkm.tools.links._get_note_neighbors_data",
        lambda _vault, note_id, include_semantic: {
            "note_id": note_id,
            "outbound": [],
            "inbound": [],
            "semantic": [],
        },
    )

    result = graph_cli("graph", "neighbors", "lonely", "--format", "table")

    assert result.exit_code == 0, result.output
    assert "No connections found for 'lonely'" in result.output


def test_graph_neighbors_missing_graph_exits_with_index_guidance(
    graph_cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing graph data fails closed with the indexing remediation."""

    def missing_graph(_vault, _note_id: str, _include_semantic: bool):
        raise FileNotFoundError("graph.json")

    monkeypatch.setattr("pkm.tools.links._get_note_neighbors_data", missing_graph)

    result = graph_cli("graph", "neighbors", "note-a")

    assert result.exit_code == 1
    assert "graph.json not found" in result.output
    assert "pkm index" in result.output


def test_graph_neighbors_table_renders_semantic_confidence(
    graph_cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Semantic neighbor rows include their confidence when semantic mode is enabled."""
    calls: list[tuple[str, bool]] = []

    def fake_neighbors(_vault, note_id: str, include_semantic: bool):
        calls.append((note_id, include_semantic))
        return {
            "note_id": note_id,
            "outbound": [],
            "inbound": [],
            "semantic": [
                {
                    "note_id": "semantic-peer",
                    "title": "Semantic Peer",
                    "type": "note",
                    "confidence": 0.876,
                }
            ],
        }

    monkeypatch.setattr("pkm.tools.links._get_note_neighbors_data", fake_neighbors)

    result = graph_cli(
        "graph",
        "neighbors",
        "seed-note",
        "--semantic",
        "--format",
        "table",
    )

    assert result.exit_code == 0, result.output
    assert calls == [("seed-note", True)]
    assert "Neighbors of seed-note" in result.output
    assert "semantic-peer" in result.output
    assert "Semantic Peer" in result.output
    assert "semantic (0.88)" in result.output
