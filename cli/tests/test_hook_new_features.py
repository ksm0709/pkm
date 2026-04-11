"""Tests for new hook.py features: migrate, updated setup, turn-end-exit2."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from pkm.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def vault_env(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULTS_ROOT", str(tmp_vault.path.parent))
    monkeypatch.setenv("PKM_DEFAULT_VAULT", tmp_vault.name)
    return tmp_vault


# ---------------------------------------------------------------------------
# pkm hook migrate
# ---------------------------------------------------------------------------


def test_migrate_removes_pkm_hooks_keeps_omc(tmp_path, monkeypatch):
    """migrate removes PKM hooks but keeps OMC and other hooks intact."""
    settings = {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "pkm hook run session-start --format system-reminder",
                        }
                    ]
                },
                {
                    "matcher": "startup",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "/path/to/omc/session-start-hook.js",
                            "timeout": 15,
                        }
                    ],
                },
            ],
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "pkm agent hook turn-start --format system-reminder",
                        }
                    ]
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "pkm hook run turn-end",
                        }
                    ]
                },
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "/path/to/omc/stop-hook.js",
                            "timeout": 10,
                        }
                    ]
                },
            ],
        }
    }
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.json"
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    # Patch Path.home() to return our tmp_path
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = CliRunner().invoke(main, ["hook", "migrate"])
    assert result.exit_code == 0, result.output

    updated = json.loads(settings_path.read_text(encoding="utf-8"))
    hooks = updated["hooks"]

    # SessionStart: only OMC hook remains (PKM hook removed)
    ss_hooks = [h for m in hooks["SessionStart"] for h in m.get("hooks", [])]
    assert not any("pkm" in h.get("command", "") for h in ss_hooks)
    assert any("omc" in h.get("command", "") for h in ss_hooks)

    # UserPromptSubmit: entire matcher dropped (only had PKM hook)
    ups_hooks = [
        h for m in hooks.get("UserPromptSubmit", []) for h in m.get("hooks", [])
    ]
    assert not any("pkm" in h.get("command", "") for h in ups_hooks)

    # Stop: only OMC hook remains
    stop_hooks = [h for m in hooks["Stop"] for h in m.get("hooks", [])]
    assert not any("pkm" in h.get("command", "") for h in stop_hooks)
    assert any("omc" in h.get("command", "") for h in stop_hooks)

    # Output reports removed counts
    assert "Removed" in result.output


def test_migrate_dry_run_does_not_write(tmp_path, monkeypatch):
    """migrate --dry-run shows changes without writing."""
    settings = {
        "hooks": {
            "Stop": [
                {"hooks": [{"type": "command", "command": "pkm hook run turn-end"}]}
            ]
        }
    }
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.json"
    original_text = json.dumps(settings)
    settings_path.write_text(original_text, encoding="utf-8")

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = CliRunner().invoke(main, ["hook", "migrate", "--dry-run"])
    assert result.exit_code == 0
    assert "Would remove" in result.output
    assert "Dry run" in result.output
    # File must be unchanged
    assert settings_path.read_text(encoding="utf-8") == original_text


def test_migrate_no_settings_file(tmp_path, monkeypatch):
    """migrate handles missing settings.json gracefully."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = CliRunner().invoke(main, ["hook", "migrate"])
    assert result.exit_code == 0
    assert "not found" in result.output


def test_migrate_no_pkm_hooks(tmp_path, monkeypatch):
    """migrate reports nothing to do when no PKM hooks present."""
    settings = {
        "hooks": {
            "Stop": [
                {"hooks": [{"type": "command", "command": "/path/to/omc/stop-hook.js"}]}
            ]
        }
    }
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.json"
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = CliRunner().invoke(main, ["hook", "migrate"])
    assert result.exit_code == 0
    assert "nothing to remove" in result.output


# ---------------------------------------------------------------------------
# pkm hook setup --tool claude-code (now prints instructions, no file write)
# ---------------------------------------------------------------------------


def test_setup_claude_code_writes_settings_json(tmp_path, monkeypatch):
    """setup --tool claude-code merges PKM hooks into ~/.claude/settings.json."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = CliRunner().invoke(main, ["hook", "setup", "--tool", "claude-code"])
    assert result.exit_code == 0, result.output

    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.exists()
    import json as _json

    data = _json.loads(settings_path.read_text())
    assert "SessionStart" in data["hooks"]
    assert "pkm hook run session-start" in str(data["hooks"]["SessionStart"])
    assert "pkm hook remove" in result.output


def test_setup_codex_prints_install_instructions(tmp_path, monkeypatch):
    """setup --tool codex prints copy/symlink instructions for codex/hooks.json."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = CliRunner().invoke(main, ["hook", "setup", "--tool", "codex"])
    assert result.exit_code == 0
    assert "codex" in result.output.lower()
    assert "hooks.json" in result.output
    assert "Written:" in result.output


# ---------------------------------------------------------------------------
# pkm hook run turn-end-exit2
# ---------------------------------------------------------------------------


def test_turn_end_exit2_guard_active_exits_0(runner, vault_env):
    """turn-end-exit2 exits 0 when stop_hook_active guard is set."""
    payload = json.dumps(
        {
            "stop_hook_active": True,
            "transcript_path": "/some/path.jsonl",
            "session_id": "abc",
        }
    )
    result = runner.invoke(main, ["hook", "run", "turn-end-exit2"], input=payload)
    assert result.exit_code == 0


def test_turn_end_exit2_no_transcript_exits_0(runner, vault_env):
    """turn-end-exit2 exits 0 when transcript_path is missing."""
    payload = json.dumps({"stop_hook_active": False, "session_id": "abc"})
    result = runner.invoke(main, ["hook", "run", "turn-end-exit2"], input=payload)
    assert result.exit_code == 0


def test_turn_end_exit2_with_transcript_exits_2(runner, vault_env):
    """turn-end-exit2 exits 2 and writes instructions to stderr when transcript_path present."""
    payload = json.dumps(
        {
            "stop_hook_active": False,
            "transcript_path": "/tmp/session.jsonl",
            "session_id": "abc",
        }
    )
    result = runner.invoke(main, ["hook", "run", "turn-end-exit2"], input=payload)
    assert result.exit_code == 2
    # CliRunner merges stderr into output — check combined output for instructions
    assert "KNOWLEDGE EXTRACTION" in result.output
    assert "pkm daily add" in result.output
