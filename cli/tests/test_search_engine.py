"""Tests for pkm.search_engine."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from pkm.config import VaultConfig
from pkm.search_engine import (
    IndexEntry,
    SearchResult,
    VectorIndex,
    build_index,
    is_index_stale,
    load_index,
    search,
)


@pytest.fixture
def mock_model(monkeypatch):
    """Replace SentenceTransformer with a deterministic fake model."""

    class FakeModel:
        def encode(self, texts, **kwargs):
            import numpy as np

            texts_list = texts if isinstance(texts, list) else [texts]
            return np.array(
                [[hash(t) % 100 / 100.0] * 384 for t in texts_list]
            )

    monkeypatch.setattr("pkm.search_engine._require_transformers", lambda name: FakeModel())


def test_build_index(tmp_vault: VaultConfig, mock_model):
    """build_index creates index.json with one entry per note."""
    index = build_index(tmp_vault)

    index_path = tmp_vault.pkm_dir / "index.json"
    assert index_path.exists(), "index.json should be created"

    data = json.loads(index_path.read_text(encoding="utf-8"))
    assert "entries" in data
    assert len(data["entries"]) == len(index.entries)
    assert len(index.entries) > 0

    # Every entry must have required fields
    for entry in index.entries:
        assert entry.note_id
        assert isinstance(entry.embedding, list)
        assert len(entry.embedding) == 384


def test_load_index(tmp_vault: VaultConfig, mock_model):
    """load_index returns a VectorIndex matching what was saved."""
    original = build_index(tmp_vault)
    loaded = load_index(tmp_vault)

    assert loaded.model == original.model
    assert len(loaded.entries) == len(original.entries)
    entry_ids = {e.note_id for e in loaded.entries}
    for e in original.entries:
        assert e.note_id in entry_ids


def test_load_index_missing_raises(tmp_vault: VaultConfig):
    """load_index raises ClickException when index.json doesn't exist."""
    import click

    with pytest.raises(click.ClickException, match="pkm index"):
        load_index(tmp_vault)


def test_search_returns_results(tmp_vault: VaultConfig, mock_model):
    """search returns sorted SearchResult list."""
    index = build_index(tmp_vault)
    results = search("MVCC 동시성", index, top_n=5)

    assert isinstance(results, list)
    assert len(results) <= 5
    for r in results:
        assert isinstance(r, SearchResult)
        assert r.rank >= 1

    # Ranks should be sequential starting at 1
    ranks = [r.rank for r in results]
    assert ranks == list(range(1, len(results) + 1))


def test_search_backlink_tiebreaker(tmp_vault: VaultConfig, monkeypatch):
    """When scores are equal, higher backlink_count ranks first."""
    import numpy as np

    fixed_emb = [0.5] * 384

    class TiedModel:
        def encode(self, texts, **kwargs):
            texts_list = texts if isinstance(texts, list) else [texts]
            return np.array([fixed_emb for _ in texts_list])

    monkeypatch.setattr("pkm.search_engine._require_transformers", lambda name: TiedModel())

    # Build index so all embeddings are identical (score ties guaranteed)
    index = build_index(tmp_vault)

    # Manually set different backlink counts
    index.entries[0].backlink_count = 10
    index.entries[1].backlink_count = 0

    results = search("anything", index, top_n=len(index.entries))
    # Entry with higher backlink count must come first
    assert results[0].backlink_count >= results[1].backlink_count


def test_is_index_stale_no_index(tmp_vault: VaultConfig):
    """is_index_stale returns True when index.json doesn't exist."""
    assert is_index_stale(tmp_vault) is True


def test_is_index_stale_fresh(tmp_vault: VaultConfig, mock_model):
    """is_index_stale returns False right after build."""
    build_index(tmp_vault)
    assert is_index_stale(tmp_vault) is False


def test_is_index_stale_detects_new_file(tmp_vault: VaultConfig, mock_model):
    """is_index_stale returns True when a newer .md exists."""
    build_index(tmp_vault)

    # Create a new note after building the index
    new_note = tmp_vault.notes_dir / "brand-new.md"
    new_note.write_text(
        "---\nid: brand-new\naliases: []\ntags: []\n---\nNew note.\n",
        encoding="utf-8",
    )

    assert is_index_stale(tmp_vault) is True


def test_graceful_import_error(tmp_vault: VaultConfig, monkeypatch):
    """build_index raises ClickException when sentence-transformers is not installed."""
    import click

    def _missing(_name):
        raise click.ClickException("sentence-transformers is not installed. Run: pkm setup")

    monkeypatch.setattr("pkm.search_engine._require_transformers", _missing)

    with pytest.raises(click.ClickException, match="sentence-transformers"):
        build_index(tmp_vault)
