"""Tests for tools/tags.py — list_tags, tag_search."""

from __future__ import annotations

import asyncio
import json

import pytest

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


@pytest.mark.parametrize(
    "pattern, min_count, expected_mode",
    [
        ("database", 2, "exact"),
        ("data*", 1, "glob"),
        ("database+postgresql", 1, "AND"),
        ("database,untagged", 2, "OR"),
    ],
)
def test_tag_search_patterns(tmp_vault, monkeypatch, pattern, min_count, expected_mode):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(tag_search(pattern=pattern)))
    assert result["count"] >= min_count
    assert expected_mode in result["mode"]


def test_tag_search_no_match_returns_empty(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(tag_search(pattern="nonexistent-tag-xyz")))
    assert result["count"] == 0
    assert result["results"] == []
