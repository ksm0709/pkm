"""Tests for pkm.search_engine."""

from __future__ import annotations

import json

import pytest

from pkm.config import VaultConfig
from pkm.search_engine import (
    IndexEntry,
    SearchResult,
    VectorIndex,
    _extract_created_at,
    build_index,
    is_index_stale,
    load_index,
    search,
)
from pkm._memory_types import CURRENT_SCHEMA_VERSION


@pytest.fixture
def mock_model(monkeypatch):
    """Replace SentenceTransformer with a deterministic fake model."""

    class FakeModel:
        def encode(self, texts, **kwargs):
            import numpy as np

            texts_list = texts if isinstance(texts, list) else [texts]
            return np.array([[hash(t) % 100 / 100.0] * 384 for t in texts_list])

    monkeypatch.setattr(
        "pkm.search_engine._require_transformers", lambda name: FakeModel()
    )


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
    results = search("MVCC concurrency", index, top_n=5)

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

    monkeypatch.setattr(
        "pkm.search_engine._require_transformers", lambda name: TiedModel()
    )

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
        raise click.ClickException(
            "sentence-transformers is not installed. Run: pkm setup"
        )

    monkeypatch.setattr("pkm.search_engine._require_transformers", _missing)

    with pytest.raises(click.ClickException, match="sentence-transformers"):
        build_index(tmp_vault)


# --- New schema v2 tests ---


def test_load_index_field_filtering(tmp_vault: VaultConfig):
    """load_index does not crash when index.json has unknown extra fields."""
    tmp_vault.pkm_dir.mkdir(parents=True, exist_ok=True)
    index_path = tmp_vault.pkm_dir / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "model": "all-MiniLM-L6-v2",
                "created_at": "2024-01-01T00:00:00Z",
                "schema_version": CURRENT_SCHEMA_VERSION,
                "entries": [
                    {
                        "note_id": "note-1",
                        "path": "/vault/note-1.md",
                        "embedding": [0.1] * 384,
                        "backlink_count": 0,
                        "tags": [],
                        "title": "Note 1",
                        "unknown_future_field": "should be ignored",
                        "another_unknown": 42,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    index = load_index(tmp_vault)
    assert len(index.entries) == 1
    assert index.entries[0].note_id == "note-1"


def test_load_index_old_schema_uses_defaults(tmp_vault: VaultConfig):
    """load_index applies defaults for missing v2 fields when loading old index."""
    tmp_vault.pkm_dir.mkdir(parents=True, exist_ok=True)
    index_path = tmp_vault.pkm_dir / "index.json"
    # Old v1 index: no memory_type, importance, created_at, schema_version
    index_path.write_text(
        json.dumps(
            {
                "model": "all-MiniLM-L6-v2",
                "created_at": "2024-01-01T00:00:00Z",
                "entries": [
                    {
                        "note_id": "note-1",
                        "path": "/vault/note-1.md",
                        "embedding": [0.1] * 384,
                        "backlink_count": 2,
                        "tags": ["test"],
                        "title": "Note 1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    index = load_index(tmp_vault)
    assert index.schema_version == 1
    entry = index.entries[0]
    assert entry.memory_type is None
    assert entry.importance == 5.0
    assert entry.created_at is None


def test_is_index_stale_schema_version_mismatch(tmp_vault: VaultConfig):
    """is_index_stale returns True when schema_version differs from CURRENT_SCHEMA_VERSION."""
    tmp_vault.pkm_dir.mkdir(parents=True, exist_ok=True)
    index_path = tmp_vault.pkm_dir / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "model": "all-MiniLM-L6-v2",
                "created_at": "2024-01-01T00:00:00Z",
                "schema_version": 1,  # old version
                "entries": [],
            }
        ),
        encoding="utf-8",
    )
    assert is_index_stale(tmp_vault) is True


def test_is_index_stale_current_schema(tmp_vault: VaultConfig):
    """is_index_stale returns False when schema_version matches and no new files."""
    tmp_vault.pkm_dir.mkdir(parents=True, exist_ok=True)
    index_path = tmp_vault.pkm_dir / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "model": "all-MiniLM-L6-v2",
                "created_at": "2024-01-01T00:00:00Z",
                "schema_version": CURRENT_SCHEMA_VERSION,
                "entries": [],
            }
        ),
        encoding="utf-8",
    )
    # No .md files newer than index
    assert is_index_stale(tmp_vault) is False


def test_extract_created_at_from_frontmatter(tmp_path):
    """_extract_created_at returns frontmatter created_at when present."""
    note_path = tmp_path / "some-note.md"
    note_path.touch()
    result = _extract_created_at(note_path, {"created_at": "2024-03-15T10:00:00+00:00"})
    assert result == "2024-03-15T10:00:00+00:00"


def test_extract_created_at_from_filename(tmp_path):
    """_extract_created_at falls back to YYYY-MM-DD from filename."""
    note_path = tmp_path / "2024-03-15-my-note.md"
    note_path.touch()
    result = _extract_created_at(note_path, {})
    assert result == "2024-03-15T00:00:00+00:00"


def test_extract_created_at_no_date(tmp_path):
    """_extract_created_at returns None when no date available."""
    note_path = tmp_path / "untitled-note.md"
    note_path.touch()
    result = _extract_created_at(note_path, {})
    assert result is None


def _make_index_with_entries(entries: list[IndexEntry]) -> VectorIndex:
    return VectorIndex(
        model="all-MiniLM-L6-v2",
        created_at="2024-01-01T00:00:00Z",
        entries=entries,
        schema_version=CURRENT_SCHEMA_VERSION,
    )


def test_search_memory_type_filter(monkeypatch):
    """search() with memory_type_filter returns only entries with matching type."""
    import numpy as np

    class FakeModel:
        def encode(self, texts, **kwargs):
            texts_list = texts if isinstance(texts, list) else [texts]
            return np.array([[0.5] * 384 for _ in texts_list])

    monkeypatch.setattr(
        "pkm.search_engine._require_transformers", lambda name: FakeModel()
    )

    entries = [
        IndexEntry(
            note_id="ep-1",
            path="/ep-1.md",
            embedding=[0.5] * 384,
            backlink_count=0,
            tags=[],
            title="Episodic",
            memory_type="episodic",
        ),
        IndexEntry(
            note_id="sem-1",
            path="/sem-1.md",
            embedding=[0.5] * 384,
            backlink_count=0,
            tags=[],
            title="Semantic",
            memory_type="semantic",
        ),
        IndexEntry(
            note_id="ep-2",
            path="/ep-2.md",
            embedding=[0.5] * 384,
            backlink_count=0,
            tags=[],
            title="Episodic 2",
            memory_type="episodic",
        ),
    ]
    index = _make_index_with_entries(entries)
    results = search("test", index, memory_type_filter="episodic")
    assert len(results) == 2
    assert all(r.memory_type == "episodic" for r in results)


def test_search_min_importance_filter(monkeypatch):
    """search() with min_importance filters out low-importance entries."""
    import numpy as np

    class FakeModel:
        def encode(self, texts, **kwargs):
            texts_list = texts if isinstance(texts, list) else [texts]
            return np.array([[0.5] * 384 for _ in texts_list])

    monkeypatch.setattr(
        "pkm.search_engine._require_transformers", lambda name: FakeModel()
    )

    entries = [
        IndexEntry(
            note_id="low",
            path="/low.md",
            embedding=[0.5] * 384,
            backlink_count=0,
            tags=[],
            title="Low",
            importance=2.0,
        ),
        IndexEntry(
            note_id="high",
            path="/high.md",
            embedding=[0.5] * 384,
            backlink_count=0,
            tags=[],
            title="High",
            importance=8.0,
        ),
    ]
    index = _make_index_with_entries(entries)
    results = search("test", index, min_importance=5.0)
    assert len(results) == 1
    assert results[0].note_id == "high"


def test_search_recency_weight_prefers_recent(monkeypatch):
    """search() with recency_weight > 0 scores recent entries higher than old ones."""
    import numpy as np

    class FakeModel:
        def encode(self, texts, **kwargs):
            texts_list = texts if isinstance(texts, list) else [texts]
            return np.array([[0.5] * 384 for _ in texts_list])

    monkeypatch.setattr(
        "pkm.search_engine._require_transformers", lambda name: FakeModel()
    )

    # Recent: 1 hour ago, Old: 10000 hours ago
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    recent_ts = (now - timedelta(hours=1)).isoformat()
    old_ts = (now - timedelta(hours=10000)).isoformat()

    entries = [
        IndexEntry(
            note_id="old",
            path="/old.md",
            embedding=[0.5] * 384,
            backlink_count=0,
            tags=[],
            title="Old",
            created_at=old_ts,
            importance=5.0,
        ),
        IndexEntry(
            note_id="recent",
            path="/recent.md",
            embedding=[0.5] * 384,
            backlink_count=0,
            tags=[],
            title="Recent",
            created_at=recent_ts,
            importance=5.0,
        ),
    ]
    index = _make_index_with_entries(entries)
    results = search("test", index, recency_weight=0.5)
    assert results[0].note_id == "recent"


def test_search_time_decay(monkeypatch):
    """Entry created 1 hour ago scores higher than entry created 1000 hours ago."""
    import numpy as np
    from datetime import datetime, timezone, timedelta

    class FakeModel:
        def encode(self, texts, **kwargs):
            texts_list = texts if isinstance(texts, list) else [texts]
            return np.array([[0.5] * 384 for _ in texts_list])

    monkeypatch.setattr(
        "pkm.search_engine._require_transformers", lambda name: FakeModel()
    )

    now = datetime.now(timezone.utc)
    entry_1h = IndexEntry(
        note_id="1h",
        path="/1h.md",
        embedding=[0.5] * 384,
        backlink_count=0,
        tags=[],
        title="1h ago",
        created_at=(now - timedelta(hours=1)).isoformat(),
        importance=5.0,
    )
    entry_1000h = IndexEntry(
        note_id="1000h",
        path="/1000h.md",
        embedding=[0.5] * 384,
        backlink_count=0,
        tags=[],
        title="1000h ago",
        created_at=(now - timedelta(hours=1000)).isoformat(),
        importance=5.0,
    )
    index = _make_index_with_entries([entry_1h, entry_1000h])
    results = search("test", index, recency_weight=1.0)

    score_1h = next(r.score for r in results if r.note_id == "1h")
    score_1000h = next(r.score for r in results if r.note_id == "1000h")
    assert score_1h > score_1000h
