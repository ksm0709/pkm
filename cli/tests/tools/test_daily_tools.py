"""Tests for tools/daily.py — read_daily_log offset/date_str semantics."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path

from pkm.tools.daily import add_daily_log, create_daily_subnote, read_daily_log


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


def test_add_daily_log_success_and_error_paths(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))

    ok = _run(add_daily_log(text="tool log entry"))
    assert "Successfully added daily log" in ok
    assert "tool log entry" in ok

    monkeypatch.setattr(
        "pkm.tools.daily.add_daily_entry",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("daily locked")),
    )
    err = _run(add_daily_log(text="blocked"))
    assert "Error adding daily log: daily locked" in err


def test_read_daily_log_reports_read_errors(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    today = date.today().isoformat()
    daily_path = tmp_vault.daily_dir / f"{today}.md"
    daily_path.write_text("unreadable", encoding="utf-8")
    original_read_text = Path.read_text

    def fail_today(self, *args, **kwargs):
        if self == daily_path:
            raise OSError("permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_today)

    result = _run(read_daily_log())
    assert "Error reading daily note: permission denied" in result


def test_create_daily_subnote_validates_title_and_links_daily(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))

    empty = _run(create_daily_subnote(title="../", content="ignored"))
    assert empty == "Error: title cannot be empty."

    result = _run(
        create_daily_subnote(
            title="Research Followup",
            content="Subnote body",
            tags=["research"],
            aliases=["follow"],
        )
    )

    assert "Created subnote:" in result
    created_name = result.removeprefix("Created subnote: ").strip()
    subnote = tmp_vault.daily_dir / created_name
    assert subnote.exists()
    assert "Subnote body" in subnote.read_text(encoding="utf-8")
    today = date.today().isoformat()
    assert f"[[{subnote.stem}]]" in (tmp_vault.daily_dir / f"{today}.md").read_text(
        encoding="utf-8"
    )


def test_create_daily_subnote_reports_write_errors(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    original_write_text = Path.write_text

    def fail_subnote_write(self, *args, **kwargs):
        if self.name.endswith("write-fails.md"):
            raise OSError("disk full")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_subnote_write)

    result = _run(create_daily_subnote(title="write fails", content="body"))
    assert "Error creating subnote: disk full" in result
