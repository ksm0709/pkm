"""Tests for new hook.py features: migrate, updated setup, turn-end-exit2."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.commands import hook as hook_mod


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
    assert "UserPromptSubmit" not in data["hooks"]
    assert "pkm hook remove" in result.output


def test_setup_claude_code_prunes_only_stale_prompt_submit(tmp_path, monkeypatch):
    """setup removes old PKM prompt-submit hooks without touching other events."""
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir()
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "pkm hook run session-start --format system-reminder",
                                }
                            ]
                        }
                    ],
                    "UserPromptSubmit": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "pkm hook run turn-start --format system-reminder",
                                },
                                {
                                    "type": "command",
                                    "command": "pkm agent hook turn-start --format system-reminder",
                                },
                                {
                                    "type": "prompt",
                                    "prompt": "You are a PKM context injector. Return additionalContext.",
                                },
                                {
                                    "type": "command",
                                    "command": "/path/to/non-pkm-prompt-hook",
                                },
                                {
                                    "type": "prompt",
                                    "prompt": "Return additionalContext when the user asks about pkm workflows.",
                                },
                            ]
                        }
                    ],
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "pkm hook run turn-end-exit2",
                                }
                            ]
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = CliRunner().invoke(main, ["hook", "setup", "--tool", "claude-code"])
    assert result.exit_code == 0, result.output
    assert "Removed 3 stale PKM hook(s) from UserPromptSubmit" in result.output

    data = json.loads(settings_path.read_text())
    assert "pkm hook run session-start" in str(data["hooks"]["SessionStart"])
    assert "pkm hook run turn-end-exit2" in str(data["hooks"]["Stop"])
    assert "/path/to/non-pkm-prompt-hook" in str(data["hooks"]["UserPromptSubmit"])
    assert "asks about pkm workflows" in str(data["hooks"]["UserPromptSubmit"])
    assert "turn-start" not in str(data["hooks"]["UserPromptSubmit"])
    assert "PKM context injector" not in str(data["hooks"]["UserPromptSubmit"])


def test_setup_codex_prints_install_instructions(tmp_path, monkeypatch):
    """setup --tool codex prints copy/symlink instructions for codex/hooks.json."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = CliRunner().invoke(main, ["hook", "setup", "--tool", "codex"])
    assert result.exit_code == 0
    assert "codex" in result.output.lower()
    assert "hooks.json" in result.output
    assert "Written:" in result.output
    data = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    assert "UserPromptSubmit" not in data["hooks"]


def test_setup_codex_prunes_only_stale_prompt_submit(tmp_path, monkeypatch):
    """codex setup also reconciles old PKM prompt-submit hooks."""
    hooks_path = tmp_path / ".codex" / "hooks.json"
    hooks_path.parent.mkdir()
    hooks_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "pkm hook run session-start --format system-reminder",
                                }
                            ]
                        }
                    ],
                    "UserPromptSubmit": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "pkm hook run turn-start --format system-reminder",
                                },
                                {
                                    "type": "command",
                                    "command": "/path/to/non-pkm-prompt-hook",
                                },
                            ]
                        }
                    ],
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "bash /path/to/pkm/codex/hooks/stop.sh",
                                }
                            ]
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = CliRunner().invoke(main, ["hook", "setup", "--tool", "codex"])
    assert result.exit_code == 0, result.output
    assert "Removed 1 stale PKM hook(s) from UserPromptSubmit" in result.output

    data = json.loads(hooks_path.read_text())
    assert "pkm hook run session-start" in str(data["hooks"]["SessionStart"])
    assert "codex/hooks/stop.sh" in str(data["hooks"]["Stop"])
    assert "/path/to/non-pkm-prompt-hook" in str(data["hooks"]["UserPromptSubmit"])
    assert "turn-start" not in str(data["hooks"]["UserPromptSubmit"])


def test_packaged_hook_configs_do_not_install_prompt_submit():
    """Packaged hook artifacts should not reinstall prompt-submit context injection."""
    repo_root = Path(__file__).resolve().parents[2]
    for rel_path in ("plugin/hooks/hooks.json", "codex/hooks.json"):
        data = json.loads((repo_root / rel_path).resolve().read_text())
        assert "UserPromptSubmit" not in data["hooks"]


# ---------------------------------------------------------------------------
# pkm hook run turn-end-exit2
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload_dict, expected_exit",
    [
        (
            {
                "stop_hook_active": True,
                "transcript_path": "/some/path.jsonl",
                "session_id": "abc",
            },
            0,
        ),
        ({"stop_hook_active": False, "session_id": "abc"}, 0),
        (
            {
                "stop_hook_active": False,
                "transcript_path": "/tmp/session.jsonl",
                "session_id": "abc",
            },
            0,
        ),
    ],
)
def test_turn_end_exit2_behaviors(runner, vault_env, payload_dict, expected_exit):
    """turn-end-exit2 behaves correctly based on payload."""
    payload = json.dumps(payload_dict)
    result = runner.invoke(main, ["hook", "run", "turn-end-exit2"], input=payload)
    assert result.exit_code == expected_exit
    # Claude Code with transcript: silently exits 0, no output (protocol in SKILL.md)
    has_transcript = payload_dict.get("transcript_path") and not payload_dict.get(
        "stop_hook_active"
    )
    if has_transcript:
        assert result.output.strip() == ""


# ---------------------------------------------------------------------------
# turn-start footer: top_note_id injection
# ---------------------------------------------------------------------------


class _FakeNote:
    """Minimal SearchResult stand-in."""

    def __init__(self, title: str, importance: float, memory_type: str = "semantic"):
        self.title = title
        self.importance = importance
        self.memory_type = memory_type


def test_turn_start_footer_injects_top_note_id(runner, vault_env, monkeypatch):
    """When search returns results, footer contains the highest-imp note_id (not <slug>)."""
    notes = [
        _FakeNote("low-note", 5.0),
        _FakeNote("top-note-abc", 8.0),
        _FakeNote("mid-note", 6.0),
    ]
    monkeypatch.setattr("pkm.search_engine.search_via_daemon", lambda *a, **kw: notes)
    monkeypatch.setattr("pkm.commands.hook._detect_pkm_mcp", lambda: True)

    payload = json.dumps({"user_prompt": "test topic", "session_id": "s1"})
    result = runner.invoke(
        main, ["hook", "run", "turn-start", "--format", "plain"], input=payload
    )
    assert result.exit_code == 0, result.output
    assert 'note_id="top-note-abc"' in result.output
    assert "<slug>" not in result.output


def test_turn_start_footer_fallback_slug_when_no_results(
    runner, vault_env, monkeypatch
):
    """When search returns no results, footer keeps generic <slug> placeholder."""
    monkeypatch.setattr("pkm.search_engine.search_via_daemon", lambda *a, **kw: [])
    monkeypatch.setattr("pkm.commands.hook._detect_pkm_mcp", lambda: True)

    payload = json.dumps({"user_prompt": "test topic", "session_id": "s1"})
    result = runner.invoke(
        main, ["hook", "run", "turn-start", "--format", "plain"], input=payload
    )
    assert result.exit_code == 0, result.output
    assert "<slug>" in result.output


def test_turn_start_footer_fallback_slug_when_search_fails(
    runner, vault_env, monkeypatch
):
    """When search raises an exception, footer falls back to generic <slug>."""

    def _failing_search(*a, **kw):
        raise RuntimeError("search unavailable")

    monkeypatch.setattr("pkm.search_engine.search_via_daemon", _failing_search)
    monkeypatch.setattr("pkm.commands.hook._detect_pkm_mcp", lambda: True)

    payload = json.dumps({"user_prompt": "test topic", "session_id": "s1"})
    result = runner.invoke(
        main, ["hook", "run", "turn-start", "--format", "plain"], input=payload
    )
    assert result.exit_code == 0, result.output
    assert "<slug>" in result.output


def test_turn_start_search_query_uses_user_prompt_not_daily_context(
    runner, vault_env, tmp_vault, monkeypatch
):
    """Daily snippets should be recent context only, not noise in note search queries."""
    today_path = tmp_vault.daily_dir / f"{date.today().isoformat()}.md"
    today_path.write_text(
        "---\nid: today\n---\n\n## Logs\n"
        "- [09:00] unrelated daily contamination about 2026-07-08 releases\n",
        encoding="utf-8",
    )
    captured_queries: list[str] = []

    def _capture_search(query, *args, **kwargs):
        captured_queries.append(query)
        return [_FakeNote("battery-note", 5.0)]

    monkeypatch.setattr("pkm.search_engine.search_via_daemon", _capture_search)
    monkeypatch.setattr("pkm.commands.hook._detect_pkm_mcp", lambda: True)

    payload = json.dumps(
        {"extra": {"platform": "hermes", "user_message": "[Taeho] 2차전지 찾아줘"}}
    )
    result = runner.invoke(
        main, ["hook", "run", "turn-start", "--format", "plain"], input=payload
    )

    assert result.exit_code == 0, result.output
    assert captured_queries == ["2차전지 찾아줘"]


def test_session_start_consumes_zettel_signal_and_uses_mcp_reference(
    runner, vault_env, monkeypatch
):
    """Session-start surfaces daemon zettel signals once and switches to MCP guidance."""
    signal = vault_env.pkm_dir / "zettel-pending"
    signal.write_text(json.dumps({"marked": 2}), encoding="utf-8")
    monkeypatch.setattr("pkm.commands.hook._detect_pkm_mcp", lambda: True)
    monkeypatch.setattr(
        "pkm.commands.hook._check_consolidation_trigger", lambda *a: None
    )

    result = runner.invoke(main, ["hook", "run", "session-start", "--format", "plain"])

    assert result.exit_code == 0, result.output
    assert "Zettel Loop Ready" in result.output
    assert "Daemon auto-consolidated 2 daily note(s)" in result.output
    assert "Use MCP tools for all PKM operations" in result.output
    assert not signal.exists()


def test_session_start_ignores_consolidation_failures(runner, vault_env, monkeypatch):
    """Session-start still emits PKM guidance when consolidation policy fails."""
    monkeypatch.setattr(
        "pkm.commands.hook._check_consolidation_trigger",
        lambda *a: (_ for _ in ()).throw(RuntimeError("state failed")),
    )

    result = runner.invoke(main, ["hook", "run", "session-start", "--format", "plain"])

    assert result.exit_code == 0, result.output
    assert "## PKM" in result.output


def test_turn_start_falls_back_to_local_search_and_note_description(
    runner, vault_env, tmp_vault, monkeypatch
):
    """Turn-start falls back from daemon search and enriches results from note files."""
    note_path = tmp_vault.notes_dir / "fallback-result.md"
    note_path.write_text(
        "---\nid: fallback-result\ndescription: Result description from file\n---\n\nBody\n",
        encoding="utf-8",
    )
    search_result = SimpleNamespace(
        title="Fallback Result",
        importance=7.0,
        memory_type="semantic",
        path=str(note_path),
    )
    monkeypatch.setattr("pkm.search_engine.search_via_daemon", lambda *a, **kw: None)
    monkeypatch.setattr("pkm.search_engine.load_index", lambda vault: object())
    monkeypatch.setattr("pkm.search_engine.search", lambda *a, **kw: [search_result])
    monkeypatch.setattr("pkm.commands.hook._detect_pkm_mcp", lambda: False)

    payload = json.dumps({"extra": {"platform": "hermes", "user_message": "fallback"}})
    result = runner.invoke(
        main, ["hook", "run", "turn-start", "--format", "plain"], input=payload
    )

    assert result.exit_code == 0, result.output
    assert "## Relevant Notes" in result.output
    assert "Fallback Result" in result.output
    assert "Result description from file" in result.output


def test_turn_start_swallows_daily_and_tail_failures(
    runner, vault_env, tmp_vault, monkeypatch
):
    """Daily context read/tail failures do not suppress the hook advisory."""
    today_path = tmp_vault.daily_dir / f"{date.today().isoformat()}.md"
    today_path.write_text("daily content", encoding="utf-8")
    original_read_text = Path.read_text

    def fail_today_read(self, *args, **kwargs):
        if self == today_path:
            raise OSError("daily unreadable")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_today_read)
    monkeypatch.setattr(
        "pkm.commands.hook._tail_daily_entries",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("tail failed")),
    )

    result = runner.invoke(main, ["hook", "run", "turn-start", "--format", "plain"])

    assert result.exit_code == 0, result.output
    assert "# PKM Context" in result.output


def test_turn_end_appends_summary_to_existing_daily_with_session(
    runner, vault_env, tmp_vault
):
    """Turn-end appends summaries with session tags when today's daily exists."""
    today = date.today().isoformat()
    daily_path = tmp_vault.daily_dir / f"{today}.md"
    daily_path.write_text("# Today\n\n- [08:00] existing\n", encoding="utf-8")

    result = runner.invoke(
        main,
        [
            "hook",
            "run",
            "turn-end",
            "--session",
            "sess-123",
            "--summary",
            "captured learning",
        ],
    )

    assert result.exit_code == 0, result.output
    text = daily_path.read_text(encoding="utf-8")
    assert "- [08:00] existing" in text
    assert "[session:sess-123] captured learning" in text


def test_turn_end_exit2_opencode_plugin_returns_block_json(runner, vault_env):
    """OpenCode stop hooks receive a structured block response instead of exit 2."""
    payload = json.dumps({"hook_source": "opencode-plugin", "stop_hook_active": False})

    result = runner.invoke(main, ["hook", "run", "turn-end-exit2"], input=payload)

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["decision"] == "block"
    assert data["stop_hook_active"] is True
    assert "Knowledge Extraction" in data["inject_prompt"]


def test_turn_end_exit2_invalid_payload_emits_sidecar_instructions(runner, vault_env):
    """Invalid/no-transcript payloads fall back to stdout instructions for sidecars."""
    result = runner.invoke(main, ["hook", "run", "turn-end-exit2"], input="{bad json")

    assert result.exit_code == 0
    assert "[pkm hook run turn-end-exit2]" in result.output
    assert "Knowledge Extraction" in result.output


def test_hook_debug_command_toggles_visible_mode(runner, vault_env):
    """Debug command writes hooks.debug and reports the selected visibility mode."""
    result_on = runner.invoke(main, ["hook", "debug", "on"])
    result_off = runner.invoke(main, ["hook", "debug", "off"])

    assert result_on.exit_code == 0, result_on.output
    assert "Hook debug mode: ON" in result_on.output
    assert result_off.exit_code == 0, result_off.output
    assert "Hook debug mode: OFF" in result_off.output
    assert "debug = false" in (vault_env.pkm_dir / "config.toml").read_text(
        encoding="utf-8"
    )


def test_hook_run_debug_mode_forces_plain_output(runner, vault_env):
    """hooks.debug=true keeps hook output visible even if system-reminder is requested."""
    (vault_env.pkm_dir / "config.toml").write_text(
        "[hooks]\ndebug = true\n", encoding="utf-8"
    )

    result = runner.invoke(
        main, ["hook", "run", "session-start", "--format", "system-reminder"]
    )

    assert result.exit_code == 0, result.output
    assert not result.output.startswith("<system-reminder>")
    assert "## PKM" in result.output


def test_hook_run_without_resolvable_vault_exits_successfully(runner, monkeypatch):
    """Vault-free hook execution remains non-blocking when no vault can be resolved."""
    monkeypatch.delenv("PKM_VAULTS_ROOT", raising=False)
    monkeypatch.delenv("PKM_DEFAULT_VAULT", raising=False)
    monkeypatch.setattr(
        "pkm.config.get_vault",
        lambda name=None: (_ for _ in ()).throw(RuntimeError("no vault")),
    )

    result = runner.invoke(main, ["hook", "run", "session-start"])

    assert result.exit_code == 0
    assert "## PKM" in result.output


def test_hook_debug_reports_missing_vault(runner, monkeypatch):
    """Debug toggling reports a clear error when no active vault exists."""
    monkeypatch.setattr(
        "pkm.config.get_vault",
        lambda name=None: (_ for _ in ()).throw(RuntimeError("no vault")),
    )

    result = runner.invoke(main, ["hook", "debug", "on"])

    assert result.exit_code == 0
    assert "Error: no active vault found." in result.output


def test_parse_daily_entries_returns_empty_when_read_fails(tmp_vault, monkeypatch):
    """Daily entry parsing treats unreadable files as missing context."""
    daily_path = tmp_vault.daily_dir / "unreadable.md"
    daily_path.write_text("- [09:00] hidden\n", encoding="utf-8")
    original_read_text = Path.read_text

    def fail_daily_read(self, *args, **kwargs):
        if self == daily_path:
            raise OSError("unreadable")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_daily_read)

    assert hook_mod._parse_daily_entries(daily_path) == []


def test_hook_remove_command_dry_run_filters_pkm_prompt_hooks(
    runner, tmp_path, monkeypatch
):
    """`hook remove` uses the remove path and recognizes prompt-only PKM hooks."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir()
    settings = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {"type": "agent", "prompt": "PKM extraction prompt"},
                        {"type": "command", "command": "echo keep"},
                    ]
                }
            ]
        }
    }
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    result = runner.invoke(main, ["hook", "remove", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "Would remove 1 PKM hook(s) from Stop" in result.output
    assert "Dry run" in result.output
    assert json.loads(settings_path.read_text(encoding="utf-8")) == settings


def test_hook_remove_invalid_settings_json_reports_error(runner, tmp_path, monkeypatch):
    """Remove reports invalid Claude settings instead of crashing."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir()
    settings_path.write_text("{bad json", encoding="utf-8")

    result = runner.invoke(main, ["hook", "remove"])

    assert result.exit_code == 0
    assert "Error reading settings.json" in result.output


def test_hook_setup_all_dry_run_runs_both_tools_with_separator(
    runner, tmp_path, monkeypatch
):
    """No-tool setup shows both Claude and Codex sections without writing user files."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = runner.invoke(main, ["hook", "setup", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "PKM Claude Code hooks" in result.output
    assert "PKM Codex hooks" in result.output
    assert "─" in result.output
    assert "Dry run" in result.output


def test_hook_setup_claude_invalid_settings_reports_error(
    runner, tmp_path, monkeypatch
):
    """Claude hook setup reports invalid existing JSON and leaves it untouched."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir()
    settings_path.write_text("{bad json", encoding="utf-8")

    result = runner.invoke(main, ["hook", "setup", "--tool", "claude-code"])

    assert result.exit_code == 0
    assert "Error reading settings.json" in result.output


def test_hook_setup_codex_source_read_error_is_reported(runner, tmp_path, monkeypatch):
    """Codex hook setup reports packaged hook read failures."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    original_read_text = Path.read_text

    def fail_packaged_hooks(self, *args, **kwargs):
        if self.name == "hooks.json" and self.parent.name == "codex":
            raise OSError("packaged hooks missing")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_packaged_hooks)

    result = runner.invoke(main, ["hook", "setup", "--tool", "codex"])

    assert result.exit_code == 0
    assert "Error reading PKM codex hooks" in result.output


def test_hook_setup_codex_invalid_existing_config_reports_error(
    runner, tmp_path, monkeypatch
):
    """Codex hook setup reports invalid existing user hook JSON."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    hooks_path = tmp_path / ".codex" / "hooks.json"
    hooks_path.parent.mkdir()
    hooks_path.write_text("{bad json", encoding="utf-8")

    result = runner.invoke(main, ["hook", "setup", "--tool", "codex"])

    assert result.exit_code == 0
    assert "Error reading ~/.codex/hooks.json" in result.output


def test_hook_setup_codex_dry_run_and_idempotent_skip(runner, tmp_path, monkeypatch):
    """Codex setup supports dry-run additions and idempotent skip reporting."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    dry_run = runner.invoke(main, ["hook", "setup", "--tool", "codex", "--dry-run"])
    first_write = runner.invoke(main, ["hook", "setup", "--tool", "codex"])
    second_write = runner.invoke(main, ["hook", "setup", "--tool", "codex"])

    assert dry_run.exit_code == 0, dry_run.output
    assert "Dry run" in dry_run.output
    assert first_write.exit_code == 0, first_write.output
    assert "Written:" in first_write.output
    assert second_write.exit_code == 0, second_write.output
    assert "Already installed" in second_write.output
    assert "nothing to do" in second_write.output.lower()
