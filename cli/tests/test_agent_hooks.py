"""Tests for pkm agent hook commands."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def vault_env(tmp_vault: VaultConfig, monkeypatch):
    """Set PKM_DEFAULT_VAULT and PKM_VAULTS_ROOT so CLI finds the tmp vault."""
    monkeypatch.setenv("PKM_VAULTS_ROOT", str(tmp_vault.path.parent))
    monkeypatch.setenv("PKM_DEFAULT_VAULT", tmp_vault.name)
    return tmp_vault


# ---------------------------------------------------------------------------
# session-start
# ---------------------------------------------------------------------------


def test_session_start_plain(runner, vault_env):
    """session-start --format plain outputs plain text."""
    result = runner.invoke(
        main, ["agent", "hook", "session-start", "--format", "plain"]
    )
    assert result.exit_code == 0
    output = result.output
    # No system-reminder tags in plain mode
    assert "<system-reminder>" not in output
    assert "</system-reminder>" not in output
    # Some content present
    assert len(output.strip()) > 0


def test_session_start_system_reminder(runner, vault_env):
    """session-start --format system-reminder wraps output in tags."""
    result = runner.invoke(
        main, ["agent", "hook", "session-start", "--format", "system-reminder"]
    )
    assert result.exit_code == 0
    # Output may include deprecation warning prefix; check contains, not startswith
    assert "<system-reminder>" in result.output
    assert "</system-reminder>" in result.output


def test_session_start_includes_daily_notes(runner, vault_env, tmp_vault: VaultConfig):
    """session-start includes recent daily notes when they exist."""
    # Create a daily note for yesterday
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    daily_path = tmp_vault.daily_dir / f"{yesterday}.md"
    daily_path.write_text(
        f"---\nid: {yesterday}\ntags: []\n---\nImportant session context here.\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        main, ["agent", "hook", "session-start", "--format", "plain"]
    )
    assert result.exit_code == 0
    assert "Recent Daily Notes" in result.output
    assert yesterday in result.output


def test_session_start_no_daily_notes(runner, vault_env, tmp_vault: VaultConfig):
    """session-start works gracefully when no recent daily notes exist."""
    # Remove all daily notes from the last 3 days
    for i in range(1, 4):
        d = (date.today() - timedelta(days=i)).isoformat()
        p = tmp_vault.daily_dir / f"{d}.md"
        if p.exists():
            p.unlink()

    result = runner.invoke(main, ["agent", "hook", "session-start"])
    assert result.exit_code == 0
    # Should still produce output (fallback message)
    assert len(result.output.strip()) > 0


def test_session_start_search_failure_does_not_crash(runner, vault_env, monkeypatch):
    """session-start silently skips search when index is missing."""
    # No index.json exists — load_index would raise ClickException
    result = runner.invoke(main, ["agent", "hook", "session-start"])
    assert result.exit_code == 0  # Must not crash


# ---------------------------------------------------------------------------
# turn-start
# ---------------------------------------------------------------------------


def test_turn_start_plain(runner, vault_env):
    """turn-start --format plain outputs memory command reminders."""
    result = runner.invoke(main, ["agent", "hook", "turn-start", "--format", "plain"])
    assert result.exit_code == 0
    assert "pkm daily add" in result.output
    assert "pkm note add" in result.output
    assert "pkm note show" in result.output
    assert "pkm" in result.output and "skill" in result.output
    assert "PKM Role" in result.output


def test_turn_start_system_reminder(runner, vault_env):
    """turn-start --format system-reminder wraps output."""
    result = runner.invoke(
        main, ["agent", "hook", "turn-start", "--format", "system-reminder"]
    )
    assert result.exit_code == 0
    # Output may include deprecation warning prefix; check contains, not startswith
    assert "<system-reminder>" in result.output
    assert "</system-reminder>" in result.output


def test_turn_start_with_session(runner, vault_env):
    """turn-start --session includes session ID in output."""
    result = runner.invoke(
        main, ["agent", "hook", "turn-start", "--session", "abc-123"]
    )
    assert result.exit_code == 0
    assert "abc-123" in result.output


def test_turn_start_without_session(runner, vault_env):
    """turn-start without --session omits session line."""
    result = runner.invoke(main, ["agent", "hook", "turn-start"])
    assert result.exit_code == 0
    assert "Session:" not in result.output


# ---------------------------------------------------------------------------
# turn-end
# ---------------------------------------------------------------------------


def test_turn_end_no_summary_emits_guide(runner, vault_env):
    """turn-end without --summary still emits preservation guide (always-emit behavior)."""
    result = runner.invoke(main, ["agent", "hook", "turn-end"])
    assert result.exit_code == 0
    # Now always emits preservation guide even without --summary
    assert len(result.output.strip()) > 0


def test_turn_end_appends_to_existing_daily_note(
    runner, vault_env, tmp_vault: VaultConfig
):
    """turn-end --summary appends an entry to today's daily note."""
    today = date.today().isoformat()
    daily_path = tmp_vault.daily_dir / f"{today}.md"
    daily_path.write_text(f"# {today}\n\n- 09:00 existing entry\n", encoding="utf-8")

    result = runner.invoke(
        main, ["agent", "hook", "turn-end", "--summary", "finished task X"]
    )
    assert result.exit_code == 0

    content = daily_path.read_text(encoding="utf-8")
    assert "finished task X" in content
    assert "existing entry" in content  # original preserved


def test_turn_end_creates_daily_note_if_missing(
    runner, vault_env, tmp_vault: VaultConfig
):
    """turn-end --summary creates today's daily note if it doesn't exist."""
    today = date.today().isoformat()
    daily_path = tmp_vault.daily_dir / f"{today}.md"
    if daily_path.exists():
        daily_path.unlink()

    result = runner.invoke(
        main, ["agent", "hook", "turn-end", "--summary", "completed work Y"]
    )
    assert result.exit_code == 0
    assert daily_path.exists()
    content = daily_path.read_text(encoding="utf-8")
    assert "completed work Y" in content


def test_turn_end_includes_session_tag(runner, vault_env, tmp_vault: VaultConfig):
    """turn-end --session includes [session:ID] in the entry."""
    result = runner.invoke(
        main,
        [
            "agent",
            "hook",
            "turn-end",
            "--session",
            "sess-42",
            "--summary",
            "did something",
        ],
    )
    assert result.exit_code == 0
    today = date.today().isoformat()
    content = (tmp_vault.daily_dir / f"{today}.md").read_text(encoding="utf-8")
    assert "[session:sess-42]" in content


def test_turn_end_timestamp_format(runner, vault_env, tmp_vault: VaultConfig):
    """turn-end entry includes HH:MM timestamp."""
    result = runner.invoke(
        main, ["agent", "hook", "turn-end", "--summary", "timestamp test"]
    )
    assert result.exit_code == 0
    today = date.today().isoformat()
    content = (tmp_vault.daily_dir / f"{today}.md").read_text(encoding="utf-8")
    # Should contain HH:MM pattern
    import re

    assert re.search(r"\d{2}:\d{2}", content)


# ---------------------------------------------------------------------------
# _safe_hook
# ---------------------------------------------------------------------------


def test_safe_hook_catches_exception(runner, vault_env, monkeypatch):
    """_safe_hook catches exceptions and exits 0 (hook crash protection)."""
    from pkm.commands.hook import _safe_hook
    import click

    @click.command()
    @_safe_hook
    def buggy_cmd():
        raise RuntimeError("intentional failure")

    test_runner = CliRunner()
    result = test_runner.invoke(buggy_cmd)
    # Should exit 0 despite exception
    assert result.exit_code == 0


def test_safe_hook_logs_to_stderr(runner):
    """_safe_hook writes error to stderr."""
    from pkm.commands.hook import _safe_hook
    import click

    @click.command()
    @_safe_hook
    def bad_cmd():
        raise ValueError("test error message")

    test_runner = CliRunner()
    result = test_runner.invoke(bad_cmd)
    assert result.exit_code == 0
    # CliRunner merges stderr into output by default; error message appears somewhere
    assert "test error message" in result.output


# ---------------------------------------------------------------------------
# setup-hooks --dry-run
# ---------------------------------------------------------------------------


def test_setup_hooks_claude_code_dry_run(runner, vault_env, tmp_path, monkeypatch):
    """setup-hooks --tool claude-code prints plugin install instructions (no longer writes settings.json)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(
        main, ["agent", "setup-hooks", "--tool", "claude-code", "--dry-run"]
    )
    assert result.exit_code == 0
    output = result.output
    # New behavior: prints plugin install instructions, not JSON config
    assert "PKM Claude Code Plugin" in output
    assert "plugin" in output.lower()
    assert "pkm hook migrate" in output


def test_setup_hooks_codex_dry_run(runner, vault_env):
    """setup-hooks --tool codex prints codex/hooks.json install instructions."""
    result = runner.invoke(
        main, ["agent", "setup-hooks", "--tool", "codex", "--dry-run"]
    )
    assert result.exit_code == 0
    # New behavior: prints copy/symlink instructions for codex/hooks.json
    assert "hooks.json" in result.output
    assert "codex" in result.output.lower()


def test_setup_hooks_claude_code_no_file_write(runner, vault_env, tmp_path, monkeypatch):
    """setup-hooks --tool claude-code no longer writes to settings.json — prints instructions only."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    result = runner.invoke(main, ["agent", "setup-hooks", "--tool", "claude-code"])
    assert result.exit_code == 0

    # Must NOT create settings.json
    settings_path = fake_home / ".claude" / "settings.json"
    assert not settings_path.exists()
    # Must print plugin install instructions
    assert "PKM Claude Code Plugin" in result.output
