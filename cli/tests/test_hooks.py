"""Tests for pkm hook commands (new primary interface)."""
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
    monkeypatch.setenv("PKM_VAULTS_ROOT", str(tmp_vault.path.parent))
    monkeypatch.setenv("PKM_DEFAULT_VAULT", tmp_vault.name)
    return tmp_vault


# ---------------------------------------------------------------------------
# pkm hook run session-start
# ---------------------------------------------------------------------------

def test_hook_run_session_start_plain(runner, vault_env):
    result = runner.invoke(main, ["hook", "run", "session-start", "--format", "plain"])
    assert result.exit_code == 0
    assert "<system-reminder>" not in result.output
    assert len(result.output.strip()) > 0


def test_hook_run_session_start_system_reminder(runner, vault_env):
    result = runner.invoke(main, ["hook", "run", "session-start", "--format", "system-reminder"])
    assert result.exit_code == 0
    assert result.output.startswith("<system-reminder>")
    assert result.output.strip().endswith("</system-reminder>")


def test_hook_run_session_start_with_daily_notes(runner, vault_env, tmp_vault):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    (tmp_vault.daily_dir / f"{yesterday}.md").write_text(
        f"---\nid: {yesterday}\ntags: []\n---\nImportant context here.\n",
        encoding="utf-8",
    )
    result = runner.invoke(main, ["hook", "run", "session-start"])
    assert result.exit_code == 0
    assert "Recent Daily Notes" in result.output


def test_hook_run_session_start_ignores_irrelevant_options(runner, vault_env):
    """--summary is irrelevant for session-start and must be silently ignored."""
    result = runner.invoke(main, ["hook", "run", "session-start", "--summary", "ignored"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# pkm hook run turn-start
# ---------------------------------------------------------------------------

def test_hook_run_turn_start_includes_search_instruction(runner, vault_env):
    result = runner.invoke(main, ["hook", "run", "turn-start", "--format", "plain"])
    assert result.exit_code == 0
    assert "pkm search" in result.output
    assert "--tags" in result.output
    assert "pkm" in result.output and "skill" in result.output
    assert "PKM Role" in result.output


def test_hook_run_turn_start_no_format_json_mention(runner, vault_env):
    """turn-start must NOT mention --format json (json is the default)."""
    result = runner.invoke(main, ["hook", "run", "turn-start"])
    assert result.exit_code == 0
    assert "--format json" not in result.output


def test_hook_run_turn_start_system_reminder(runner, vault_env):
    result = runner.invoke(main, ["hook", "run", "turn-start", "--format", "system-reminder"])
    assert result.exit_code == 0
    assert result.output.startswith("<system-reminder>")
    assert result.output.strip().endswith("</system-reminder>")


def test_hook_run_turn_start_with_session(runner, vault_env):
    result = runner.invoke(main, ["hook", "run", "turn-start", "--session", "sess-xyz"])
    assert result.exit_code == 0
    assert "sess-xyz" in result.output


# ---------------------------------------------------------------------------
# pkm hook run turn-end
# ---------------------------------------------------------------------------

def test_hook_run_turn_end_always_emits(runner, vault_env):
    """turn-end must emit preservation guide even without --summary."""
    result = runner.invoke(main, ["hook", "run", "turn-end"])
    assert result.exit_code == 0
    assert len(result.output.strip()) > 0
    assert "pkm daily add" in result.output or "preserve" in result.output.lower()


def test_hook_run_turn_end_includes_slash_commands(runner, vault_env):
    result = runner.invoke(main, ["hook", "run", "turn-end"])
    assert result.exit_code == 0
    assert "/pkm:memory-store" in result.output
    assert "/pkm:distill-daily" in result.output
    assert "/pkm:zettel-loop" in result.output


def test_hook_run_turn_end_with_summary_writes_daily(runner, vault_env, tmp_vault):
    today = date.today().isoformat()
    daily_path = tmp_vault.daily_dir / f"{today}.md"
    result = runner.invoke(main, ["hook", "run", "turn-end", "--summary", "test summary xyz"])
    assert result.exit_code == 0
    assert daily_path.exists()
    assert "test summary xyz" in daily_path.read_text(encoding="utf-8")


def test_hook_run_turn_end_system_reminder(runner, vault_env):
    result = runner.invoke(main, ["hook", "run", "turn-end", "--format", "system-reminder"])
    assert result.exit_code == 0
    assert result.output.startswith("<system-reminder>")
    assert result.output.strip().endswith("</system-reminder>")


# ---------------------------------------------------------------------------
# pkm hook setup (non-destructive registration)
# ---------------------------------------------------------------------------

def test_hook_setup_dry_run_claude_code(runner, vault_env, tmp_path, monkeypatch):
    """dry-run with fresh HOME shows only pkm hook run commands."""
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(main, ["hook", "setup", "--tool", "claude-code", "--dry-run"])
    assert result.exit_code == 0
    assert "pkm hook run session-start" in result.output
    assert "pkm hook run turn-start" in result.output
    assert "pkm hook run turn-end" in result.output
    assert "pkm agent hook" not in result.output


def test_hook_setup_appends_to_existing_settings(runner, vault_env, tmp_path, monkeypatch):
    """pkm hook setup must NOT overwrite existing hooks (omc coexistence)."""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    existing_hook_cmd = "omc-existing-hook --arg"
    settings.write_text(json.dumps({
        "hooks": {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": existing_hook_cmd}]}]
        }
    }), encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))

    result = runner.invoke(main, ["hook", "setup", "--tool", "claude-code"])
    assert result.exit_code == 0

    merged = json.loads(settings.read_text(encoding="utf-8"))
    matchers = merged["hooks"]["UserPromptSubmit"]
    commands = [h["command"] for m in matchers for h in m.get("hooks", [])]
    assert existing_hook_cmd in commands, "Existing hook must be preserved"
    assert any("pkm hook run turn-start" in cmd for cmd in commands), "pkm hook must be added"


def test_hook_setup_idempotent(runner, vault_env, tmp_path, monkeypatch):
    """Running hook setup twice must not duplicate hooks."""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))

    runner.invoke(main, ["hook", "setup", "--tool", "claude-code"])
    runner.invoke(main, ["hook", "setup", "--tool", "claude-code"])

    merged = json.loads(settings.read_text(encoding="utf-8"))
    for event, matchers in merged["hooks"].items():
        cmds = [h["command"] for m in matchers for h in m.get("hooks", [])]
        pkm_cmds = [c for c in cmds if "pkm hook run" in c]
        assert len(pkm_cmds) <= 1, f"Duplicate pkm hook for {event}: {pkm_cmds}"


# ---------------------------------------------------------------------------
# pkm agent deprecation warnings
# ---------------------------------------------------------------------------

def test_deprecated_agent_hook_session_start_warns(runner, vault_env):
    result = runner.invoke(main, ["agent", "hook", "session-start"])
    assert result.exit_code == 0
    assert "deprecated" in result.output.lower() or "DeprecationWarning" in (result.output + str(result.exception or ""))


def test_deprecated_agent_setup_hooks_warns(runner, vault_env, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir(parents=True)
    result = runner.invoke(main, ["agent", "setup-hooks", "--tool", "claude-code", "--dry-run"])
    assert result.exit_code == 0
