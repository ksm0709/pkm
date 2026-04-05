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

    def invoke(*args, input=None):
        monkeypatch.setattr(
            "pkm.config.discover_vaults",
            lambda root=None: {"test-vault": tmp_vault},
        )
        monkeypatch.setattr("pkm.config.load_config", lambda: {})
        return runner.invoke(main, list(args), catch_exceptions=False, input=input)

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


# ---------------------------------------------------------------------------
# daily edit helpers
# ---------------------------------------------------------------------------

import types as _types

class _FakeProc:
    """Fake subprocess.CompletedProcess for subprocess.run mocks."""
    returncode = 0

def _fake_run(calls=None):
    """Return a subprocess.run mock that records calls and returns returncode=0."""
    def _run(args):
        if calls is not None:
            calls.append(args)
        return _FakeProc()
    return _run


# ---------------------------------------------------------------------------
# daily edit
# ---------------------------------------------------------------------------

def test_daily_edit_opens_today_note(cli_runner, tmp_vault, monkeypatch):
    """daily edit opens today's daily note in editor."""
    calls = []
    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {"defaults": {"editor": "vim"}})
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", _fake_run(calls))

    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text("existing\n", encoding="utf-8")

    result = cli_runner("daily", "edit")
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert calls[0][0] == "vim"
    assert today_str in calls[0][-1]


def test_daily_edit_creates_note_if_missing(cli_runner, tmp_vault, monkeypatch):
    """daily edit creates the daily note if it doesn't exist yet."""
    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {})
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", _fake_run())

    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    assert not note_path.exists()

    result = cli_runner("daily", "edit")
    assert result.exit_code == 0, result.output
    assert note_path.exists()
    assert "## TODO" in note_path.read_text(encoding="utf-8")


def test_daily_edit_editor_from_env_visual(cli_runner, tmp_vault, monkeypatch):
    """Editor falls back to $VISUAL when config has no editor."""
    calls = []
    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {})
    monkeypatch.setenv("VISUAL", "emacs")
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", _fake_run(calls))

    result = cli_runner("daily", "edit")
    assert result.exit_code == 0
    assert calls[0][0] == "emacs"


def test_daily_edit_editor_fallback_nano(cli_runner, tmp_vault, monkeypatch):
    """Editor falls back to nano when nothing is configured."""
    calls = []
    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {})
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", _fake_run(calls))

    result = cli_runner("daily", "edit")
    assert result.exit_code == 0
    assert calls[0][0] == "nano"


def test_daily_edit_nonzero_returncode_warns(cli_runner, tmp_vault, monkeypatch):
    """daily edit warns user when editor exits with non-zero code."""
    class _FailProc:
        returncode = 1

    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {})
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", lambda args: _FailProc())

    result = cli_runner("daily", "edit")
    assert result.exit_code == 0, result.output
    assert "1" in result.output  # returncode shown


# ---------------------------------------------------------------------------
# daily edit --sub (interactive prompt)
# ---------------------------------------------------------------------------

def test_daily_edit_sub_creates_subnote(cli_runner, tmp_vault, monkeypatch):
    """daily edit --sub creates a sub-note with given title (via prompt)."""
    calls = []
    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {"defaults": {"editor": "vim"}})
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", _fake_run(calls))

    today_str = today()
    result = cli_runner("daily", "edit", "--sub", input="회의\n")
    assert result.exit_code == 0, result.output

    expected = tmp_vault.daily_dir / f"{today_str}-회의.md"
    assert expected.exists()
    assert "회의" in result.output
    assert len(calls) == 1
    assert str(expected) in calls[0][-1]


def test_daily_edit_sub_title_arg_skips_prompt(cli_runner, tmp_vault, monkeypatch):
    """daily edit --sub <title> creates sub-note without prompting."""
    calls = []
    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {})
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", _fake_run(calls))

    today_str = today()
    result = cli_runner("daily", "edit", "--sub", "아이디어")
    assert result.exit_code == 0, result.output

    expected = tmp_vault.daily_dir / f"{today_str}-아이디어.md"
    assert expected.exists()
    assert len(calls) == 1


def test_daily_edit_sub_spaces_to_hyphens(cli_runner, tmp_vault, monkeypatch):
    """daily edit --sub replaces spaces with hyphens in title."""
    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {})
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", _fake_run())

    today_str = today()
    result = cli_runner("daily", "edit", "--sub", input="my note\n")
    assert result.exit_code == 0, result.output

    expected = tmp_vault.daily_dir / f"{today_str}-my-note.md"
    assert expected.exists()


def test_daily_edit_sub_default_title_is_timestamp(cli_runner, tmp_vault, monkeypatch):
    """daily edit --sub uses HH-MM timestamp as default title when Enter pressed."""
    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {})
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", _fake_run())

    today_str = today()
    result = cli_runner("daily", "edit", "--sub", input="\n")
    assert result.exit_code == 0, result.output

    subnotes = list(tmp_vault.daily_dir.glob(f"{today_str}-*.md"))
    assert len(subnotes) == 1
    assert re.search(r"\d{2}-\d{2}", subnotes[0].stem)


def test_daily_edit_sub_existing_note_not_overwritten(cli_runner, tmp_vault, monkeypatch):
    """daily edit --sub does not overwrite an existing sub-note."""
    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {})
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", _fake_run())

    today_str = today()
    existing = tmp_vault.daily_dir / f"{today_str}-기존.md"
    existing.write_text("original content\n", encoding="utf-8")

    result = cli_runner("daily", "edit", "--sub", input="기존\n")
    assert result.exit_code == 0, result.output
    assert existing.read_text(encoding="utf-8") == "original content\n"
    assert "Opening existing" in result.output


def test_daily_edit_sub_sanitizes_path_traversal(cli_runner, tmp_vault, monkeypatch):
    """daily edit --sub strips path traversal sequences from title."""
    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {})
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", _fake_run())

    today_str = today()
    # Attempt path traversal via title
    result = cli_runner("daily", "edit", "--sub", input="../evil\n")
    assert result.exit_code == 0, result.output

    # Should sanitize to "evil" — no traversal outside daily_dir
    created = list(tmp_vault.daily_dir.glob(f"{today_str}-*.md"))
    assert len(created) == 1
    assert ".." not in created[0].name
    assert str(created[0]).startswith(str(tmp_vault.daily_dir))


# ---------------------------------------------------------------------------
# daily base — sub-note display
# ---------------------------------------------------------------------------

def test_daily_shows_subnotes_below_main(cli_runner, tmp_vault, monkeypatch):
    """pkm daily shows sub-notes below the main note with separators."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text("main content\n", encoding="utf-8")

    sub = tmp_vault.daily_dir / f"{today_str}-회의.md"
    sub.write_text("sub content\n", encoding="utf-8")

    result = cli_runner("daily")
    assert result.exit_code == 0, result.output
    assert "main content" in result.output
    assert "--- 회의 ---" in result.output
    assert "sub content" in result.output
    # Main must appear before sub-note
    assert result.output.index("main content") < result.output.index("sub content")


def test_daily_no_subnotes_output_unchanged(cli_runner, tmp_vault, monkeypatch):
    """pkm daily without sub-notes shows only the main note (no separators)."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text("just main\n", encoding="utf-8")

    result = cli_runner("daily")
    assert result.exit_code == 0, result.output
    assert "just main" in result.output
    assert "---" not in result.output
