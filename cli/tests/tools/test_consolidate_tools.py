"""Tests for tools/consolidate.py — list_consolidation_candidates, mark_consolidated."""

from __future__ import annotations

import asyncio
import json
from datetime import date


from pkm.tools.consolidate import list_consolidation_candidates, mark_consolidated


def _run(coro):
    """Run an async tool coroutine synchronously."""
    return asyncio.run(coro)


def test_candidates_includes_past_dailies(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_consolidation_candidates()))
    dates = [c["date"] for c in result["candidates"]]
    assert "2026-04-01" in dates or "2026-04-02" in dates


def test_candidates_count_field(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_consolidation_candidates()))
    assert result["count"] == len(result["candidates"])


def test_mark_consolidated_rejects_today(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    today = date.today().isoformat()
    result = _run(mark_consolidated(date_str=today, distilled_note_ids=[]))
    assert "Error" in result
    assert "today" in result.lower() or "still in use" in result.lower()


def test_mark_consolidated_rejects_missing_note_ids(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = _run(
        mark_consolidated(
            date_str="2026-04-01", distilled_note_ids=["nonexistent-note-xyz"]
        )
    )
    assert "Error" in result
    assert "nonexistent-note-xyz" in result


def test_mark_consolidated_happy_path(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(
        _run(
            mark_consolidated(
                date_str="2026-04-01", distilled_note_ids=["2026-04-01-mvcc"]
            )
        )
    )
    assert result["status"] == "consolidated"
    assert result["date"] == "2026-04-01"
    assert "2026-04-01-mvcc" in result["distilled_to"]


def test_mark_consolidated_updates_frontmatter(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    _run(
        mark_consolidated(date_str="2026-04-01", distilled_note_ids=["2026-04-01-mvcc"])
    )
    text = (tmp_vault.path / "daily" / "2026-04-01.md").read_text()
    assert "consolidated: true" in text or "consolidated: True" in text


def test_mark_consolidated_idempotent(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    _run(
        mark_consolidated(date_str="2026-04-01", distilled_note_ids=["2026-04-01-mvcc"])
    )
    result = _run(
        mark_consolidated(date_str="2026-04-01", distilled_note_ids=["2026-04-01-mvcc"])
    )
    assert "already" in result.lower() or "consolidated" in result
