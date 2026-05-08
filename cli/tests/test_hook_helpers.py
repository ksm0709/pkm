"""Scenario tests for hook helper policy and state handling."""

from __future__ import annotations

import builtins
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from pkm.commands import hook as hook_mod


def test_safe_hook_turns_unexpected_errors_into_successful_hook_exit(capsys) -> None:
    """Agent hooks should report internal failures without blocking the caller."""

    @hook_mod._safe_hook
    def failing_hook():
        raise RuntimeError("search index unavailable")

    with pytest.raises(SystemExit) as exc:
        failing_hook()

    assert exc.value.code == 0
    err = capsys.readouterr().err
    assert "[pkm hook error] search index unavailable" in err
    assert "Traceback" in err


def test_safe_hook_preserves_keyboard_interrupt_exit_code() -> None:
    """KeyboardInterrupt remains distinguishable from ordinary hook failures."""

    @hook_mod._safe_hook
    def interrupted_hook():
        raise KeyboardInterrupt

    with pytest.raises(SystemExit) as exc:
        interrupted_hook()

    assert exc.value.code == 130


def test_get_note_desc_prefers_description_then_body_and_tolerates_parse_errors(
    tmp_vault,
) -> None:
    """Search result descriptions come from note metadata, then body, then empty fallback."""
    described = tmp_vault.notes_dir / "described.md"
    described.write_text(
        "---\nid: described\ndescription: Metadata summary for display\n---\n\n"
        "Body should not win.\n",
        encoding="utf-8",
    )
    body_only = tmp_vault.notes_dir / "body-only.md"
    body_only.write_text(
        "---\nid: body-only\n---\n\nBody fallback summary for display.\n",
        encoding="utf-8",
    )
    broken = tmp_vault.notes_dir / "broken.md"
    broken.write_text("---\n: bad: yaml\n---\n", encoding="utf-8")

    assert (
        hook_mod._get_note_desc(SimpleNamespace(path=str(described)))
        == "Metadata summary for display"
    )
    assert (
        hook_mod._get_note_desc(SimpleNamespace(path=str(body_only)))
        == "Body fallback summary for display."
    )
    assert hook_mod._get_note_desc(SimpleNamespace(path=str(broken))) == ""


def test_hook_config_load_debug_and_write_paths(tmp_vault) -> None:
    """Hook config loading and debug toggling preserve existing TOML sections."""
    config_path = tmp_vault.pkm_dir / "config.toml"
    config_path.write_text(
        "[project]\nname = 'pkm'\n\n[hooks]\ndaily_tail_n = 3\n",
        encoding="utf-8",
    )

    hook_mod._write_hooks_debug(tmp_vault, True)
    text = config_path.read_text(encoding="utf-8")
    assert "[project]" in text
    assert "[hooks]\ndebug = true\ndaily_tail_n = 3" in text
    assert hook_mod._load_hook_config(tmp_vault)["hooks"]["debug"] is True
    assert hook_mod._is_debug_mode(tmp_vault) is True

    hook_mod._write_hooks_debug(tmp_vault, False)
    text = config_path.read_text(encoding="utf-8")
    assert "debug = false" in text
    assert "daily_tail_n = 3" in text
    assert hook_mod._is_debug_mode(tmp_vault) is False

    config_path.write_text("[project]\nname = 'pkm'\n", encoding="utf-8")
    hook_mod._write_hooks_debug(tmp_vault, True)
    assert "\n[hooks]\ndebug = true\n" in config_path.read_text(encoding="utf-8")


def test_hook_config_invalid_or_missing_files_are_non_debug(tmp_vault) -> None:
    """Malformed or missing hook config must not break hook execution."""
    config_path = tmp_vault.pkm_dir / "config.toml"
    if config_path.exists():
        config_path.unlink()

    assert hook_mod._load_hook_config(tmp_vault) == {}
    assert hook_mod._is_debug_mode(tmp_vault) is False

    config_path.write_text("[hooks\nnot toml", encoding="utf-8")
    assert hook_mod._load_hook_config(tmp_vault) == {}
    assert hook_mod._is_debug_mode(tmp_vault) is False


def test_is_debug_mode_tolerates_loader_failures(tmp_vault, monkeypatch) -> None:
    """Debug-mode checks are defensive around config loader failures."""
    monkeypatch.setattr(
        hook_mod,
        "_load_hook_config",
        lambda vault: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert hook_mod._is_debug_mode(tmp_vault) is False


def test_session_state_loads_defaults_and_coerces_valid_state(tmp_vault) -> None:
    """Session state recovers from bad files and normalizes valid persisted fields."""
    state_path = tmp_vault.pkm_dir / "session_state.json"
    if state_path.exists():
        state_path.unlink()

    assert hook_mod._load_session_state(tmp_vault) == {
        "session_count": 0,
        "last_consolidation_at": None,
    }

    state_path.write_text("[]", encoding="utf-8")
    assert hook_mod._load_session_state(tmp_vault)["session_count"] == 0

    state_path.write_text("{{bad json", encoding="utf-8")
    assert hook_mod._load_session_state(tmp_vault)["last_consolidation_at"] is None

    state_path.write_text(
        '{"session_count": "4", "last_consolidation_at": "2026-05-08T00:00:00"}',
        encoding="utf-8",
    )
    state = hook_mod._load_session_state(tmp_vault)
    assert state == {
        "session_count": 4,
        "last_consolidation_at": "2026-05-08T00:00:00",
    }


def test_save_session_state_swallows_filesystem_errors(tmp_vault, monkeypatch) -> None:
    """State persistence failures should not block hook startup."""
    original_write_text = Path.write_text

    def fail_session_state_write(self, *args, **kwargs):
        if self.name == "session_state.json":
            raise OSError("read only")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_session_state_write)

    hook_mod._save_session_state(tmp_vault, {"session_count": 1})


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"extra": {"platform": "hermes", "user_message": "hermes prompt"}},
            "hermes prompt",
        ),
        (
            {"prompt": "claude prompt", "extra": {"platform": "claude-code"}},
            "claude prompt",
        ),
        (
            {"hook_source": "opencode-plugin", "prompt": "opencode prompt"},
            "opencode prompt",
        ),
        ({"extra": {"input": "codex input"}}, "codex input"),
        ({"userPrompt": "camel prompt"}, "camel prompt"),
        ({"extra": {"text": "  spaced fallback  "}}, "spaced fallback"),
        ({"extra": {"prompt": "extra wins"}, "prompt": "top prompt"}, "extra wins"),
        ({"extra": {"prompt": "   "}, "text": "top text"}, "top text"),
        ({}, ""),
    ],
)
def test_extract_user_prompt_covers_platforms_and_fallbacks(payload, expected) -> None:
    """Prompt extraction supports known hook platforms and conservative fallbacks."""
    assert hook_mod._extract_user_prompt(payload) == expected


def test_consolidation_trigger_respects_disabled_auto_trigger(tmp_vault) -> None:
    """Opting out of auto-trigger leaves session state untouched."""
    result = hook_mod._check_consolidation_trigger(
        tmp_vault, {"consolidation": {"auto_trigger": False}}
    )

    assert result is None
    assert not (tmp_vault.pkm_dir / "session_state.json").exists()


def test_consolidation_trigger_persists_below_threshold_count(tmp_vault) -> None:
    """Below-threshold sessions are counted for a future recommendation."""
    result = hook_mod._check_consolidation_trigger(
        tmp_vault, {"consolidation": {"session_threshold": 3}}
    )

    assert result is None
    state = json.loads((tmp_vault.pkm_dir / "session_state.json").read_text())
    assert state["session_count"] == 1


def test_consolidation_trigger_honors_naive_datetime_cooldown(tmp_vault) -> None:
    """Cooldown parsing treats naive timestamps as UTC and suppresses early repeats."""
    state_path = tmp_vault.pkm_dir / "session_state.json"
    state_path.write_text(
        json.dumps(
            {
                "session_count": 5,
                "last_consolidation_at": datetime.now().isoformat(),
            }
        ),
        encoding="utf-8",
    )

    result = hook_mod._check_consolidation_trigger(
        tmp_vault,
        {"consolidation": {"session_threshold": 2, "cooldown_hours": 24}},
    )

    assert result is None
    state = json.loads(state_path.read_text())
    assert state["session_count"] == 6


def test_consolidation_trigger_resets_count_when_no_candidates(
    tmp_vault, monkeypatch
) -> None:
    """Threshold sessions without eligible daily notes reset instead of nagging."""
    state_path = tmp_vault.pkm_dir / "session_state.json"
    state_path.write_text(
        json.dumps({"session_count": 4, "last_consolidation_at": None}),
        encoding="utf-8",
    )
    monkeypatch.setattr("pkm.commands.consolidate._list_candidate_dates", lambda v: [])

    result = hook_mod._check_consolidation_trigger(
        tmp_vault, {"consolidation": {"session_threshold": 5}}
    )

    assert result is None
    state = json.loads(state_path.read_text())
    assert state["session_count"] == 0


def test_consolidation_trigger_lists_candidates_and_truncates_long_output(
    tmp_vault, monkeypatch
) -> None:
    """A mature session window emits a bounded consolidation recommendation."""
    state_path = tmp_vault.pkm_dir / "session_state.json"
    state_path.write_text(
        json.dumps(
            {
                "session_count": 4,
                "last_consolidation_at": "not-a-date",
            }
        ),
        encoding="utf-8",
    )
    candidates = [f"2026-05-{day:02d}" for day in range(1, 8)]
    monkeypatch.setattr(
        "pkm.commands.consolidate._list_candidate_dates", lambda v: candidates
    )

    result = hook_mod._check_consolidation_trigger(
        tmp_vault, {"consolidation": {"session_threshold": 5}}
    )

    assert result is not None
    assert "7 daily note(s) ready" in result
    assert "pkm consolidate mark 2026-05-01" in result
    assert "... and 2 more" in result
    state = json.loads(state_path.read_text())
    assert state["session_count"] == 0
    assert datetime.fromisoformat(state["last_consolidation_at"]).tzinfo is not None


def test_consolidation_trigger_swallows_internal_failures(
    tmp_vault, monkeypatch
) -> None:
    """Unexpected state/candidate failures do not break session-start hooks."""
    monkeypatch.setattr(
        hook_mod,
        "_load_session_state",
        lambda vault: (_ for _ in ()).throw(RuntimeError("state unavailable")),
    )

    assert hook_mod._check_consolidation_trigger(tmp_vault, {}) is None


def test_detect_pkm_mcp_finds_claude_settings(tmp_path, monkeypatch) -> None:
    """MCP detection checks Claude Code settings first."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        json.dumps({"mcpServers": {"pkm": {"command": "pkm"}}}),
        encoding="utf-8",
    )

    assert hook_mod._detect_pkm_mcp() is True


def test_detect_pkm_mcp_finds_hermes_yaml_config(tmp_path, monkeypatch) -> None:
    """Hermes YAML config with mcp_servers.pkm is recognized."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    hermes_dir = tmp_path / ".hermes"
    hermes_dir.mkdir()
    (hermes_dir / "config.yaml").write_text(
        "mcp_servers:\n  pkm:\n    command: pkm\n", encoding="utf-8"
    )

    assert hook_mod._detect_pkm_mcp() is True


def test_detect_pkm_mcp_uses_hermes_line_fallback_without_yaml(
    tmp_path, monkeypatch
) -> None:
    """Hermes detection still works when PyYAML is unavailable."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    hermes_dir = tmp_path / ".hermes"
    hermes_dir.mkdir()
    (hermes_dir / "config.yaml").write_text(
        "mcp_servers:\n  pkm:\n    command: pkm\n", encoding="utf-8"
    )

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("yaml unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert hook_mod._detect_pkm_mcp() is True


def test_detect_pkm_mcp_finds_opencode_config(tmp_path, monkeypatch) -> None:
    """OpenCode config with mcp.pkm is recognized."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    opencode_dir = tmp_path / ".config" / "opencode"
    opencode_dir.mkdir(parents=True)
    (opencode_dir / "opencode.json").write_text(
        json.dumps({"mcp": {"pkm": {"command": "pkm"}}}),
        encoding="utf-8",
    )

    assert hook_mod._detect_pkm_mcp() is True


def test_detect_pkm_mcp_returns_false_for_malformed_configs(
    tmp_path, monkeypatch
) -> None:
    """Malformed agent config files are ignored instead of raising."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("{bad", encoding="utf-8")
    (tmp_path / ".hermes").mkdir()
    (tmp_path / ".hermes" / "config.yaml").write_text("[", encoding="utf-8")
    opencode_dir = tmp_path / ".config" / "opencode"
    opencode_dir.mkdir(parents=True)
    (opencode_dir / "opencode.json").write_text("{bad", encoding="utf-8")

    assert hook_mod._detect_pkm_mcp() is False
