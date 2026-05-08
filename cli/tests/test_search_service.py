"""Scenario tests for daemon in-process search service contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import pkm.search_service as search_service
from pkm.config import VaultConfig
from pkm.search_engine import SearchResult, VectorIndex
from pkm.search_service import (
    STALE_INDEX_WARNING,
    get_cached_index,
    resolve_search_vault,
    run_in_process_search,
)


@pytest.fixture(autouse=True)
def clear_cached_index():
    get_cached_index.cache_clear()
    yield
    get_cached_index.cache_clear()


def _write_index(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "model": "test-model",
                "created_at": "2026-05-08T00:00:00Z",
                "schema_version": 2,
                "entries": [
                    {
                        "note_id": "note-a",
                        "path": "notes/note-a.md",
                        "embedding": [0.1, 0.2],
                        "backlink_count": 3,
                        "tags": ["search"],
                        "title": title,
                        "memory_type": "semantic",
                        "importance": 7.0,
                        "created_at": "2026-05-01T00:00:00Z",
                        "future_field": "ignored",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_cached_index_loads_entries_and_uses_mtime_cache_key(tmp_path: Path) -> None:
    """Daemon index cache loads compatible entry fields and invalidates by mtime key."""
    index_path = tmp_path / "index.json"
    _write_index(index_path, "Old Title")

    first = get_cached_index(str(index_path), 100.0)

    assert first.model == "test-model"
    assert first.schema_version == 2
    assert first.entries[0].title == "Old Title"
    assert first.entries[0].importance == 7.0
    assert not hasattr(first.entries[0], "future_field")

    _write_index(index_path, "New Title")
    cached = get_cached_index(str(index_path), 100.0)
    reloaded = get_cached_index(str(index_path), 200.0)

    assert cached is first
    assert cached.entries[0].title == "Old Title"
    assert reloaded.entries[0].title == "New Title"


def test_resolve_search_vault_uses_explicit_fallback_and_empty_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Daemon search resolves named vaults, falls back to configured default order, or None."""
    work = VaultConfig(name="work", path=tmp_path / "work")
    personal = VaultConfig(name="personal", path=tmp_path / "personal")
    monkeypatch.setattr(
        search_service,
        "discover_vaults",
        lambda: {"work": work, "personal": personal},
    )

    assert resolve_search_vault("personal") is personal
    assert resolve_search_vault("missing") is work
    assert resolve_search_vault(None) is work

    monkeypatch.setattr(search_service, "discover_vaults", lambda: {})
    assert resolve_search_vault("work") is None


@pytest.mark.anyio
async def test_run_in_process_search_missing_index_short_circuits_before_model_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing daemon index fails before model loading, cache reads, or vector search."""
    vault = VaultConfig(name="missing-index", path=tmp_path / "vault")
    vault.pkm_dir.mkdir(parents=True)
    calls: list[str] = []

    monkeypatch.setattr(search_service, "is_index_stale", lambda _vault: True)
    monkeypatch.setattr(
        search_service,
        "_require_transformers",
        lambda _model: calls.append("model"),
    )
    monkeypatch.setattr(
        search_service,
        "get_cached_index",
        lambda *_args: calls.append("cache"),
    )
    monkeypatch.setattr(
        search_service,
        "search",
        lambda **_kwargs: calls.append("search"),
    )

    with pytest.raises(FileNotFoundError):
        await run_in_process_search("mvcc", vault)

    assert calls == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("is_stale", "expected_warning"),
    [(True, STALE_INDEX_WARNING), (False, None)],
)
async def test_run_in_process_search_returns_results_and_stale_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    is_stale: bool,
    expected_warning: str | None,
) -> None:
    """In-process daemon search forwards filters and reports stale index state."""
    vault = VaultConfig(name="indexed", path=tmp_path / "vault")
    index_path = vault.pkm_dir / "index.json"
    index_path.parent.mkdir(parents=True)
    index_path.write_text("{}", encoding="utf-8")

    fake_index = VectorIndex(model="fake", created_at="now")
    fake_result = SearchResult(
        note_id="note-a",
        title="Note A",
        score=0.9,
        backlink_count=2,
        tags=["database"],
        rank=1,
    )
    calls: dict[str, object] = {}

    def fake_search(**kwargs):
        calls["search"] = kwargs
        return [fake_result]

    def fake_get_cached_index(path: str, mtime: float) -> VectorIndex:
        calls["cache"] = (path, mtime)
        return fake_index

    monkeypatch.setattr(search_service, "is_index_stale", lambda _vault: is_stale)
    monkeypatch.setattr(
        search_service,
        "_require_transformers",
        lambda model: calls.setdefault("model", model),
    )
    monkeypatch.setattr(search_service, "get_cached_index", fake_get_cached_index)
    monkeypatch.setattr(search_service, "search", fake_search)

    results, warning = await run_in_process_search(
        query="mvcc",
        vault=vault,
        top=5,
        memory_type="semantic",
        min_importance=6.5,
        recency_weight=0.25,
    )

    assert results == [fake_result]
    assert warning == expected_warning
    assert calls["model"] == "all-MiniLM-L6-v2"
    cache_path, cache_mtime = calls["cache"]
    assert cache_path == str(index_path)
    assert isinstance(cache_mtime, float)
    assert calls["search"] == {
        "query": "mvcc",
        "index": fake_index,
        "top_n": 5,
        "min_importance": 6.5,
        "memory_type_filter": "semantic",
        "recency_weight": 0.25,
    }
