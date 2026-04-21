"""Tests for find_surprising_connections in pkm.graph."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

from pkm.config import VaultConfig
from pkm.graph import find_surprising_connections


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


def _make_vault(tmp_path: Path) -> VaultConfig:
    vault_path = tmp_path / "vault"
    for d in ("notes", "daily", "tags", ".pkm"):
        (vault_path / d).mkdir(parents=True)
    return VaultConfig(name="vault", path=vault_path)


def _write_enriched(pkm_dir: Path, clusters: list[dict[str, Any]]) -> None:
    """Write a minimal graph_enriched.json with given clusters."""
    data = {
        "graph_tier": "enriched",
        "schema_version": 1,
        "clusters": clusters,
        "nodes": [],
        "links": [],
        "directed": True,
        "multigraph": False,
        "graph": {},
    }
    (pkm_dir / "graph_enriched.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_bridge_score_fields(tmp_path: Path) -> None:
    """find_surprising_connections returns dicts with expected fields."""
    vault = _make_vault(tmp_path)

    # Two clusters with different centroids
    centroid_a = _make_embedding(1)
    centroid_b = _make_embedding(2)

    _write_enriched(
        vault.pkm_dir,
        clusters=[
            {
                "id": 0,
                "centroid": centroid_a.tolist(),
                "members": ["note-a"],
                "top_tags": [],
                "is_new": False,
                "centroid_drift": None,
            },
            {
                "id": 1,
                "centroid": centroid_b.tolist(),
                "members": ["note-b"],
                "top_tags": [],
                "is_new": False,
                "centroid_drift": None,
            },
        ],
    )

    # Bridge note: midpoint between two centroids
    bridge = (centroid_a + centroid_b).astype("<f4")
    bridge /= np.linalg.norm(bridge)
    _write_vector_db(vault.pkm_dir, {"bridge-note": bridge})

    results = find_surprising_connections(vault, top_n=10)
    assert len(results) == 1
    r = results[0]
    assert r["note_id"] == "bridge-note"
    assert "bridge_score" in r
    assert "cluster_a" in r
    assert "cluster_b" in r
    assert "dist_a" in r
    assert "dist_b" in r
    assert "title" in r
    assert r["bridge_score"] > 0


def test_equidistant_scores_higher_than_cluster_interior(tmp_path: Path) -> None:
    """Equidistant note scores higher than a note deep inside one cluster (asymmetry penalty)."""
    vault = _make_vault(tmp_path)

    centroid_a = _make_embedding(10)
    centroid_b = _make_embedding(20)

    _write_enriched(
        vault.pkm_dir,
        clusters=[
            {
                "id": 0,
                "centroid": centroid_a.tolist(),
                "members": ["note-a"],
                "top_tags": [],
                "is_new": False,
                "centroid_drift": None,
            },
            {
                "id": 1,
                "centroid": centroid_b.tolist(),
                "members": ["note-b"],
                "top_tags": [],
                "is_new": False,
                "centroid_drift": None,
            },
        ],
    )

    # Interior note: very close to centroid_a (deep inside cluster A)
    interior = centroid_a.copy()

    # Bridge note: equidistant between both centroids
    bridge = (centroid_a + centroid_b).astype("<f4")
    bridge /= np.linalg.norm(bridge)

    _write_vector_db(vault.pkm_dir, {"interior-note": interior, "bridge-note": bridge})

    results = find_surprising_connections(vault, top_n=10)
    scores = {r["note_id"]: r["bridge_score"] for r in results}

    assert "bridge-note" in scores
    assert "interior-note" in scores
    assert scores["bridge-note"] > scores["interior-note"], (
        f"Expected bridge ({scores['bridge-note']:.4f}) > interior ({scores['interior-note']:.4f})"
    )


def test_top_n_limit(tmp_path: Path) -> None:
    """top_n=3 returns at most 3 results even when more notes exist."""
    vault = _make_vault(tmp_path)

    centroid_a = _make_embedding(30)
    centroid_b = _make_embedding(40)

    _write_enriched(
        vault.pkm_dir,
        clusters=[
            {
                "id": 0,
                "centroid": centroid_a.tolist(),
                "members": [],
                "top_tags": [],
                "is_new": False,
                "centroid_drift": None,
            },
            {
                "id": 1,
                "centroid": centroid_b.tolist(),
                "members": [],
                "top_tags": [],
                "is_new": False,
                "centroid_drift": None,
            },
        ],
    )

    # 10 different notes
    entries = {}
    for i in range(10):
        emb = _make_embedding(100 + i)
        entries[f"note-{i}"] = emb
    _write_vector_db(vault.pkm_dir, entries)

    results = find_surprising_connections(vault, top_n=3)
    assert len(results) <= 3


def test_no_enriched_returns_empty(tmp_path: Path) -> None:
    """No graph_enriched.json → returns empty list."""
    vault = _make_vault(tmp_path)
    # No enriched file written
    results = find_surprising_connections(vault, top_n=10)
    assert results == []


def test_less_than_two_clusters_returns_empty(tmp_path: Path) -> None:
    """Enriched file with only 1 cluster → returns empty list."""
    vault = _make_vault(tmp_path)

    centroid_a = _make_embedding(50)
    _write_enriched(
        vault.pkm_dir,
        clusters=[
            {
                "id": 0,
                "centroid": centroid_a.tolist(),
                "members": ["note-a"],
                "top_tags": [],
                "is_new": False,
                "centroid_drift": None,
            },
        ],
    )

    emb = _make_embedding(51)
    _write_vector_db(vault.pkm_dir, {"note-a": emb})

    results = find_surprising_connections(vault, top_n=10)
    assert results == []


def test_bridge_score_dedup_by_note_id(tmp_path: Path) -> None:
    """Same note_id across multiple cluster pairs → only best-scoring result kept."""
    vault = _make_vault(tmp_path)

    centroid_a = _make_embedding(60)
    centroid_b = _make_embedding(70)
    centroid_c = _make_embedding(80)

    _write_enriched(
        vault.pkm_dir,
        clusters=[
            {
                "id": 0,
                "centroid": centroid_a.tolist(),
                "members": [],
                "top_tags": [],
                "is_new": False,
                "centroid_drift": None,
            },
            {
                "id": 1,
                "centroid": centroid_b.tolist(),
                "members": [],
                "top_tags": [],
                "is_new": False,
                "centroid_drift": None,
            },
            {
                "id": 2,
                "centroid": centroid_c.tolist(),
                "members": [],
                "top_tags": [],
                "is_new": False,
                "centroid_drift": None,
            },
        ],
    )

    # One note that participates in 3 cluster pairs (0-1, 0-2, 1-2)
    bridge = (centroid_a + centroid_b + centroid_c).astype("<f4")
    bridge /= np.linalg.norm(bridge)
    _write_vector_db(vault.pkm_dir, {"multi-bridge": bridge})

    results = find_surprising_connections(vault, top_n=10)
    # Dedup: only one entry for "multi-bridge"
    note_ids = [r["note_id"] for r in results]
    assert note_ids.count("multi-bridge") == 1
