"""Tests for tools/consolidate.py — list_consolidation_candidates, mark_consolidated."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path


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


def test_candidates_entry_count_tolerates_unreadable_daily(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    original_read_text = Path.read_text

    def fail_one_daily(self, *args, **kwargs):
        if self.name == "2026-04-01.md":
            raise OSError("unreadable")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(
        "pkm.commands.consolidate._list_candidate_dates", lambda vault: ["2026-04-01"]
    )
    monkeypatch.setattr(Path, "read_text", fail_one_daily)

    result = json.loads(_run(list_consolidation_candidates()))
    candidate = next(c for c in result["candidates"] if c["date"] == "2026-04-01")
    assert candidate["entry_count"] == 0


def test_candidates_reports_discovery_errors(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    monkeypatch.setattr(
        "pkm.commands.consolidate._list_candidate_dates",
        lambda vault: (_ for _ in ()).throw(RuntimeError("candidate scan failed")),
    )

    result = _run(list_consolidation_candidates())
    assert result == "Error: candidate scan failed"


def test_mark_consolidated_requires_ids_and_existing_daily(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))

    no_ids = _run(mark_consolidated(date_str="2026-04-01", distilled_note_ids=[]))
    missing_daily = _run(
        mark_consolidated(date_str="1999-01-01", distilled_note_ids=["2026-04-01-mvcc"])
    )

    assert "distilled_note_ids is required" in no_ids
    assert "Daily note not found: 1999-01-01.md" in missing_daily


def test_mark_consolidated_reports_write_errors(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    original_write_text = Path.write_text

    def fail_daily_write(self, *args, **kwargs):
        if self.name == "2026-04-01.md":
            raise OSError("daily locked")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_daily_write)

    result = _run(
        mark_consolidated(date_str="2026-04-01", distilled_note_ids=["2026-04-01-mvcc"])
    )
    assert result == "Error: daily locked"
