"""Tests for tools/links.py — find_backlinks_for_note."""

from __future__ import annotations

import asyncio
import json


from pkm.tools.links import find_backlinks_for_note


def _run(coro):
    """Run an async tool coroutine synchronously."""
    return asyncio.run(coro)


def test_finds_backlinks_to_mvcc(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(find_backlinks_for_note(note_id="2026-04-01-mvcc")))
    note_ids = [b["note_id"] for b in result["backlinks"]]
    # database-isolation.md and concurrency-note.md both link to 2026-04-01-mvcc
    assert "database-isolation" in note_ids or "concurrency-note" in note_ids
    assert result["count"] >= 1


def test_orphan_has_no_backlinks(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(find_backlinks_for_note(note_id="isolated-note")))
    assert result["count"] == 0
    assert result["backlinks"] == []


def test_unknown_note_returns_empty(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(find_backlinks_for_note(note_id="nonexistent-note-xyz")))
    assert result["count"] == 0
    assert result["note_id"] == "nonexistent-note-xyz"


def test_backlinks_have_required_fields(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(find_backlinks_for_note(note_id="2026-04-01-mvcc")))
    for b in result["backlinks"]:
        assert "title" in b
        assert "path" in b
        assert "note_id" in b
