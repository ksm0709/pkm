"""Tests for tools/maintenance.py — vault_stats, list_stale_notes, list_orphans."""

from __future__ import annotations

import asyncio
import json


from pkm.tools.maintenance import list_orphans, list_stale_notes, vault_stats


def _run(coro):
    """Run an async tool coroutine synchronously."""
    return asyncio.run(coro)


def test_vault_stats_returns_expected_keys(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(vault_stats()))
    assert {
        "notes",
        "dailies",
        "orphans",
        "unique_tags",
        "avg_links_per_note",
        "index",
    } <= result.keys()


def test_vault_stats_note_count(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(vault_stats()))
    assert result["notes"] >= 4  # fixture has ≥4 notes


def test_vault_stats_orphan_count(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(vault_stats()))
    assert result["orphans"] >= 1  # isolated-note.md is an orphan


def test_vault_stats_empty_vault(monkeypatch, tmp_path):
    vault_path = tmp_path / "empty-vault"
    for d in ("notes", "daily", "tags", "tasks", ".pkm"):
        (vault_path / d).mkdir(parents=True)
    monkeypatch.setenv("PKM_VAULT_DIR", str(vault_path))
    result = json.loads(_run(vault_stats()))
    assert result["notes"] == 0
    assert result["orphans"] == 0


def test_list_orphans_finds_isolated_note(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_orphans()))
    filenames = [o["filename"] for o in result["orphans"]]
    assert "isolated-note.md" in filenames


def test_list_orphans_count_field(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_orphans()))
    assert result["count"] == len(result["orphans"])


def test_list_orphans_has_tags_field(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_orphans()))
    for o in result["orphans"]:
        assert "tags" in o
        assert isinstance(o["tags"], list)


def test_list_stale_notes_days_zero_returns_all(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_stale_notes(days=0)))
    assert result["count"] >= 1
    assert result["threshold_days"] == 0


def test_list_stale_notes_far_future_returns_empty(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_stale_notes(days=99999)))
    assert result["count"] == 0
    assert result["stale_notes"] == []


def test_list_stale_notes_structure(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_stale_notes(days=0)))
    for item in result["stale_notes"]:
        assert "note" in item
        assert "last_modified" in item
        assert "days_ago" in item
