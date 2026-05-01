"""Tests for tools/daily.py — read_daily_log offset/date_str semantics."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from pkm.tools.daily import read_daily_log


def _run(coro):
    return asyncio.run(coro)


def _yesterday() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


def test_read_daily_log_today_default(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    today = date.today().isoformat()
    (tmp_vault.daily_dir / f"{today}.md").write_text("TODAY-MARKER\n", encoding="utf-8")
    result = _run(read_daily_log())
    assert "TODAY-MARKER" in result


def test_read_daily_log_offset_yesterday(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    y = _yesterday()
    (tmp_vault.daily_dir / f"{y}.md").write_text("Y-MARKER\n", encoding="utf-8")
    result = _run(read_daily_log(offset=1))
    assert "Y-MARKER" in result


def test_read_daily_log_explicit_date_str(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    (tmp_vault.daily_dir / "2026-04-15.md").write_text("EXP\n", encoding="utf-8")
    result = _run(read_daily_log(date_str="2026-04-15"))
    assert "EXP" in result


def test_read_daily_log_date_str_overrides_offset(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    (tmp_vault.daily_dir / "2026-04-15.md").write_text("EXP\n", encoding="utf-8")
    result = _run(read_daily_log(date_str="2026-04-15", offset=99))
    assert "EXP" in result


def test_read_daily_log_missing_returns_message(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    y = _yesterday()
    result = _run(read_daily_log(offset=1))
    assert "No daily note found" in result
    assert y in result


def test_read_daily_log_negative_offset_returns_error(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = _run(read_daily_log(offset=-1))
    assert "Error" in result
    assert "offset" in result


def test_read_daily_log_bad_date_str_returns_error(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = _run(read_daily_log(date_str="not-a-date"))
    assert "Error" in result
