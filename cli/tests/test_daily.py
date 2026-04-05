"""Tests for daily note commands."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cli_runner(runner, tmp_vault, monkeypatch):
    """Return a runner that invokes main with the tmp_vault injected."""

    def invoke(*args):
        monkeypatch.setattr(
            "pkm.config.discover_vaults",
            lambda root=None: {"test-vault": tmp_vault},
        )
        return runner.invoke(main, list(args), catch_exceptions=False)

    return invoke


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now_hhmm() -> str:
    return datetime.now().strftime("%H:%M")


def test_daily_creates_note(cli_runner, tmp_vault):
    """daily creates today's note when it doesn't exist."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    assert not note_path.exists()

    result = cli_runner("daily")
    assert result.exit_code == 0

    assert note_path.exists()
    content = note_path.read_text(encoding="utf-8")
    assert f"id: {today_str}" in content
    assert "daily-notes" in content
    assert "## TODO" in content


def test_daily_shows_existing(cli_runner, tmp_vault):
    """daily prints content of an existing today's note."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text("existing content\n", encoding="utf-8")

    result = cli_runner("daily")
    assert result.exit_code == 0
    assert "existing content" in result.output


def test_daily_add(cli_runner, tmp_vault):
    """daily add inserts a timestamped line before ## TODO."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text(
        f"---\nid: {today_str}\naliases: []\ntags:\n  - daily-notes\n---\n\n## TODO\n",
        encoding="utf-8",
    )

    result = cli_runner("daily", "add", "작업 로그 항목")
    assert result.exit_code == 0

    content = note_path.read_text(encoding="utf-8")
    # The entry should appear before ## TODO
    log_pos = content.index("작업 로그 항목")
    todo_pos = content.index("## TODO")
    assert log_pos < todo_pos

    # Should contain timestamp pattern [HH:MM]
    assert re.search(r"\[\d{2}:\d{2}\] 작업 로그 항목", content)


def test_daily_todo(cli_runner, tmp_vault):
    """daily todo appends a timestamped line under ## TODO."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text(
        f"---\nid: {today_str}\naliases: []\ntags:\n  - daily-notes\n---\n\n## TODO\n",
        encoding="utf-8",
    )

    result = cli_runner("daily", "todo", "할 일 항목")
    assert result.exit_code == 0

    content = note_path.read_text(encoding="utf-8")
    # The entry should appear after ## TODO
    todo_pos = content.index("## TODO")
    entry_pos = content.index("할 일 항목")
    assert entry_pos > todo_pos

    assert re.search(r"\[\d{2}:\d{2}\] 할 일 항목", content)


def test_daily_add_no_todo_section(cli_runner, tmp_vault):
    """daily add works when no ## TODO section exists."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text(
        f"---\nid: {today_str}\naliases: []\ntags:\n  - daily-notes\n---\n\n로그 내용\n",
        encoding="utf-8",
    )

    result = cli_runner("daily", "add", "새 항목")
    assert result.exit_code == 0

    content = note_path.read_text(encoding="utf-8")
    assert "새 항목" in content
    assert re.search(r"\[\d{2}:\d{2}\] 새 항목", content)
