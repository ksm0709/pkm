"""Tests for build_enriched_graph and helpers in pkm.graph."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from pkm.config import VaultConfig
from pkm.graph import (
    _load_embeddings_from_vector_db,
    build_ast_and_graph,
    build_enriched_graph,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_embedding(seed: int, dims: int = 384) -> np.ndarray:
    """Deterministic unit-norm embedding."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dims).astype("<f4")
    return v / np.linalg.norm(v)


def _write_vector_db(pkm_dir: Path, entries: dict[str, np.ndarray]) -> None:
    """Write embeddings into vector.db with model='all-MiniLM-L6-v2'."""
    db_path = pkm_dir / "vector.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS vector_cache "
            "(note_id TEXT PRIMARY KEY, mtime REAL, model TEXT, embedding BLOB)"
        )
        for note_id, emb in entries.items():
            blob = np.array(emb, dtype="<f4").tobytes()
            conn.execute(
                "INSERT OR REPLACE INTO vector_cache (note_id, mtime, model, embedding) "
                "VALUES (?, ?, ?, ?)",
                (note_id, 0.0, "all-MiniLM-L6-v2", blob),
            )


def _make_minimal_vault(tmp_path: Path) -> VaultConfig:
    """Create a vault with 3 notes and a graph.json."""
    vault_path = tmp_path / "vault"
    for d in ("notes", "daily", "tags", ".pkm"):
        (vault_path / d).mkdir(parents=True)

    notes = {
        "note-a": "---\nid: note-a\naliases: []\ntags:\n  - ml\n---\nNote A content.\n",
        "note-b": "---\nid: note-b\naliases: []\ntags:\n  - ml\n---\nNote B content.\n",
        "note-c": "---\nid: note-c\naliases: []\ntags:\n  - evaluation\n---\nNote C content.\n",
    }
    for note_id, content in notes.items():
        (vault_path / "notes" / f"{note_id}.md").write_text(content, encoding="utf-8")

    vault = VaultConfig(name="vault", path=vault_path)
    build_ast_and_graph(vault)
    return vault


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_missing_graph_json_skips(tmp_vault: VaultConfig):
    """No graph.json present → graceful return, no graph_enriched.json written."""
    assert not (tmp_vault.pkm_dir / "graph.json").exists()
    build_enriched_graph(tmp_vault)  # must not raise
    assert not tmp_vault.graph_enriched_path.exists()


def test_missing_vector_db_skips(tmp_path: Path):
    """graph.json exists but vector.db missing → no graph_enriched.json written."""
    vault = _make_minimal_vault(tmp_path)
    assert vault.graph_path.exists()
    assert not (vault.pkm_dir / "vector.db").exists()

    build_enriched_graph(vault)
    assert not vault.graph_enriched_path.exists()


def test_too_few_embeddings_skips(tmp_path: Path):
    """Only 1 embedding in vector.db → no write."""
    vault = _make_minimal_vault(tmp_path)
    _write_vector_db(vault.pkm_dir, {"note-a": _make_embedding(0)})

    build_enriched_graph(vault)
    assert not vault.graph_enriched_path.exists()


def test_builds_enriched_file(tmp_path: Path):
    """Happy path: graph.json + vector.db with ≥3 notes → graph_enriched.json created."""
    vault = _make_minimal_vault(tmp_path)
    embeddings = {
        "note-a": _make_embedding(0),
        "note-b": _make_embedding(1),
        "note-c": _make_embedding(2),
    }
    _write_vector_db(vault.pkm_dir, embeddings)

    build_enriched_graph(vault, similarity_threshold=0.0)

    assert vault.graph_enriched_path.exists()
    data = json.loads(vault.graph_enriched_path.read_text())

    assert data["graph_tier"] == "enriched"
    assert data["schema_version"] == 1
    assert "built_at" in data
    assert data["model"] == "all-MiniLM-L6-v2"
    assert isinstance(data["clusters"], list)
    assert len(data["clusters"]) >= 1

    # Every cluster has required fields
    for cluster in data["clusters"]:
        assert "id" in cluster
        assert "centroid" in cluster
        assert "members" in cluster
        assert "top_tags" in cluster
        assert "is_new" in cluster
        assert "centroid_drift" in cluster


def test_similarity_threshold_effect(tmp_path: Path):
    """Threshold=0.99 excludes edges that threshold=0.0 includes."""
    vault_low = _make_minimal_vault(tmp_path / "low")
    vault_high = _make_minimal_vault(tmp_path / "high")

    embeddings = {
        "note-a": _make_embedding(10),
        "note-b": _make_embedding(11),
        "note-c": _make_embedding(12),
    }
    _write_vector_db(vault_low.pkm_dir, embeddings)
    _write_vector_db(vault_high.pkm_dir, embeddings)

    build_enriched_graph(vault_low, similarity_threshold=0.0)
    build_enriched_graph(vault_high, similarity_threshold=0.99)

    data_low = json.loads(vault_low.graph_enriched_path.read_text())
    data_high = json.loads(vault_high.graph_enriched_path.read_text())

    edge_key = "edges" if "edges" in data_low else "links"
    semantic_low = [
        e for e in data_low[edge_key] if e.get("type") == "semantic_similar"
    ]
    semantic_high = [
        e for e in data_high[edge_key] if e.get("type") == "semantic_similar"
    ]

    assert len(semantic_low) >= len(semantic_high)


def test_community_field_set_on_nodes(tmp_path: Path):
    """Every note node gets an integer 'community' attribute."""
    vault = _make_minimal_vault(tmp_path)
    embeddings = {
        "note-a": _make_embedding(20),
        "note-b": _make_embedding(21),
        "note-c": _make_embedding(22),
    }
    _write_vector_db(vault.pkm_dir, embeddings)

    build_enriched_graph(vault, similarity_threshold=0.0)

    data = json.loads(vault.graph_enriched_path.read_text())
    note_nodes = [n for n in data["nodes"] if n.get("type") == "note"]
    assert len(note_nodes) > 0
    for node in note_nodes:
        assert "community" in node, f"Node {node.get('id')} missing 'community'"
        assert isinstance(node["community"], int)


def test_drift_none_on_first_run(tmp_path: Path):
    """First run → all clusters have is_new=True and centroid_drift=None."""
    vault = _make_minimal_vault(tmp_path)
    embeddings = {
        "note-a": _make_embedding(30),
        "note-b": _make_embedding(31),
        "note-c": _make_embedding(32),
    }
    _write_vector_db(vault.pkm_dir, embeddings)

    build_enriched_graph(vault, similarity_threshold=0.0)

    data = json.loads(vault.graph_enriched_path.read_text())
    for cluster in data["clusters"]:
        assert cluster["is_new"] is True
        assert cluster["centroid_drift"] is None
        assert cluster["prev_centroid"] is None


def test_drift_computed_on_second_run(tmp_path: Path):
    """Build twice with identical vault → second run has is_new=False, centroid_drift ~ 0."""
    vault = _make_minimal_vault(tmp_path)
    embeddings = {
        "note-a": _make_embedding(40),
        "note-b": _make_embedding(41),
        "note-c": _make_embedding(42),
    }
    _write_vector_db(vault.pkm_dir, embeddings)

    # First run
    build_enriched_graph(vault, similarity_threshold=0.0)
    # Second run with same data
    build_enriched_graph(vault, similarity_threshold=0.0)

    data = json.loads(vault.graph_enriched_path.read_text())
    assert len(data["clusters"]) > 0
    for cluster in data["clusters"]:
        assert cluster["is_new"] is False
        assert cluster["centroid_drift"] is not None
        assert cluster["centroid_drift"] == pytest.approx(0.0, abs=1e-3)


def test_load_embeddings_filters_model(tmp_path: Path):
    """_load_embeddings_from_vector_db only returns all-MiniLM-L6-v2 entries."""
    vault_path = tmp_path / "vault"
    (vault_path / ".pkm").mkdir(parents=True)
    vault = VaultConfig(name="vault", path=vault_path)

    db_path = vault.pkm_dir / "vector.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS vector_cache "
            "(note_id TEXT PRIMARY KEY, mtime REAL, model TEXT, embedding BLOB)"
        )
        blob_good = np.array(_make_embedding(50), dtype="<f4").tobytes()
        blob_bad = np.array(_make_embedding(51), dtype="<f4").tobytes()
        conn.execute(
            "INSERT INTO vector_cache VALUES (?, ?, ?, ?)",
            ("good-note", 0.0, "all-MiniLM-L6-v2", blob_good),
        )
        conn.execute(
            "INSERT INTO vector_cache VALUES (?, ?, ?, ?)",
            ("other-note", 0.0, "some-other-model", blob_bad),
        )

    result = _load_embeddings_from_vector_db(vault)
    assert "good-note" in result
    assert "other-note" not in result
