"""Graph builders write JSON through atomic replacement helpers."""

from __future__ import annotations

import networkx as nx
import numpy as np

from pkm.config import VaultConfig


def test_build_ast_and_graph_writes_structural_graph_atomically(
    tmp_vault: VaultConfig, monkeypatch
) -> None:
    import pkm.graph as graph_mod

    writes = []

    def fake_atomic_write_json(path, payload, *, default=None, indent=None):
        writes.append((path, payload, default, indent))

    monkeypatch.setattr(graph_mod, "atomic_write_json", fake_atomic_write_json)

    graph_mod.build_ast_and_graph(tmp_vault)

    graph_writes = [item for item in writes if item[0] == tmp_vault.pkm_dir / "graph.json"]
    assert len(graph_writes) == 1
    assert graph_writes[0][3] == 2
    assert "nodes" in graph_writes[0][1]


def test_build_enriched_graph_writes_enriched_graph_atomically(
    tmp_vault: VaultConfig, monkeypatch
) -> None:
    import pkm.graph as graph_mod

    graph = nx.DiGraph()
    graph.add_node("note-a", type="note", title="Note A")
    graph.add_node("note-b", type="note", title="Note B")
    (tmp_vault.pkm_dir / "graph.json").write_text(
        graph_mod.json.dumps(nx.node_link_data(graph)), encoding="utf-8"
    )

    monkeypatch.setattr(
        graph_mod,
        "_load_embeddings_from_vector_db",
        lambda vault: {
            "note-a": np.array([1.0, 0.0], dtype="<f4"),
            "note-b": np.array([0.0, 1.0], dtype="<f4"),
        },
    )

    writes = []

    def fake_atomic_write_json(path, payload, *, default=None, indent=None):
        writes.append((path, payload, default, indent))

    monkeypatch.setattr(graph_mod, "atomic_write_json", fake_atomic_write_json)

    graph_mod.build_enriched_graph(tmp_vault, similarity_threshold=-1.0)

    enriched_writes = [item for item in writes if item[0] == tmp_vault.graph_enriched_path]
    assert len(enriched_writes) == 1
    assert enriched_writes[0][3] == 2
    assert enriched_writes[0][1]["graph_tier"] == "enriched"
