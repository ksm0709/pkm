"""Tests for tools/log.py — read_recent_note_activity."""

from __future__ import annotations

import asyncio


from pkm.tools.log import read_recent_note_activity


def _run(coro):
    """Run an async tool coroutine synchronously."""
    return asyncio.run(coro)


def test_missing_log_returns_no_activity(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = _run(read_recent_note_activity())
    assert result == "No activity log yet."


def test_existing_log_returns_lines(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    log_path = tmp_vault.pkm_dir / "log.md"
    log_path.write_text(
        "## 2026-04-01\n- 09:00 [create] 2026-04-01-mvcc — MVCC note\n"
        "- 10:00 [update] database-isolation — updated\n",
        encoding="utf-8",
    )
    result = _run(read_recent_note_activity(tail=10))
    assert "create" in result or "update" in result


def test_tail_limits_output(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    log_path = tmp_vault.pkm_dir / "log.md"
    lines = "\n".join(f"- line {i}" for i in range(10))
    log_path.write_text(lines, encoding="utf-8")
    result = _run(read_recent_note_activity(tail=3))
    returned_lines = [line for line in result.splitlines() if line.strip()]
    assert len(returned_lines) == 3
    assert "line 9" in result
