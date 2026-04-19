"""Tests for tools/tags.py — list_tags, tag_search."""

from __future__ import annotations

import asyncio
import json


from pkm.tools.tags import list_tags, tag_search


def _run(coro):
    """Run an async tool coroutine synchronously."""
    return asyncio.run(coro)


def test_list_tags_returns_database_tag(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_tags()))
    tag_names = [t["tag"] for t in result["tags"]]
    assert "database" in tag_names


def test_list_tags_database_count_at_least_two(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_tags()))
    db = next(t for t in result["tags"] if t["tag"] == "database")
    assert db["count"] >= 2  # mvcc + database-isolation both have database tag


def test_list_tags_count_field(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_tags()))
    assert result["count"] == len(result["tags"])


def test_tag_search_exact_match(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(tag_search(pattern="database")))
    assert result["count"] >= 2
    assert "exact" in result["mode"]


def test_tag_search_glob_pattern(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(tag_search(pattern="data*")))
    assert result["count"] >= 1
    assert "glob" in result["mode"]


def test_tag_search_and_pattern(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(tag_search(pattern="database+postgresql")))
    # Only mvcc note has both tags
    assert result["count"] >= 1
    assert "AND" in result["mode"]


def test_tag_search_or_pattern(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(tag_search(pattern="database,untagged")))
    assert result["count"] >= 2
    assert "OR" in result["mode"]


def test_tag_search_no_match_returns_empty(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(tag_search(pattern="nonexistent-tag-xyz")))
    assert result["count"] == 0
    assert result["results"] == []
