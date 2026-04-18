"""Tests for pkm hook commands (new primary interface)."""

from __future__ import annotations

import json
from datetime import date, timedelta

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
    result = runner.invoke(
        main, ["hook", "run", "session-start", "--format", "system-reminder"]
    )
    assert result.exit_code == 0
    assert result.output.startswith("<system-reminder>")
    assert result.output.strip().endswith("</system-reminder>")


def test_hook_run_session_start_no_recent_work_context(runner, vault_env, tmp_vault):
    """session-start no longer includes Recent Work Context (moved to turn-start)."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    (tmp_vault.daily_dir / f"{yesterday}.md").write_text(
        f"---\nid: {yesterday}\ntags: []\n---\nImportant context here.\n",
        encoding="utf-8",
    )
    result = runner.invoke(main, ["hook", "run", "session-start"])
    assert result.exit_code == 0
    assert "Recent Work Context" not in result.output
    assert "PKM" in result.output  # still has usage guide


def test_hook_run_session_start_ignores_irrelevant_options(runner, vault_env):
    """--summary is irrelevant for session-start and must be silently ignored."""
    result = runner.invoke(
        main, ["hook", "run", "session-start", "--summary", "ignored"]
    )
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# pkm hook run turn-start
# ---------------------------------------------------------------------------


def test_hook_run_turn_start_includes_search_instruction(runner, vault_env):
    result = runner.invoke(main, ["hook", "run", "turn-start", "--format", "plain"])
    assert result.exit_code == 0
    assert "pkm search" in result.output


def test_hook_run_turn_start_no_format_json_mention(runner, vault_env):
    """turn-start must NOT mention --format json (json is the default)."""
    result = runner.invoke(main, ["hook", "run", "turn-start"])
    assert result.exit_code == 0
    assert "--format json" not in result.output


def test_hook_run_turn_start_system_reminder(runner, vault_env):
    result = runner.invoke(
        main, ["hook", "run", "turn-start", "--format", "system-reminder"]
    )
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
    assert "pkm" in result.output.lower()


def test_hook_run_turn_end_includes_save_commands(runner, vault_env):
    result = runner.invoke(main, ["hook", "run", "turn-end"])
    assert result.exit_code == 0
    assert "pkm" in result.output
    assert "/pkm" in result.output  # references skill


def test_hook_run_turn_end_with_summary_writes_daily(runner, vault_env, tmp_vault):
    today = date.today().isoformat()
    daily_path = tmp_vault.daily_dir / f"{today}.md"
    result = runner.invoke(
        main, ["hook", "run", "turn-end", "--summary", "test summary xyz"]
    )
    assert result.exit_code == 0
    assert daily_path.exists()
    assert "test summary xyz" in daily_path.read_text(encoding="utf-8")


def test_hook_run_turn_end_system_reminder(runner, vault_env):
    result = runner.invoke(
        main, ["hook", "run", "turn-end", "--format", "system-reminder"]
    )
    assert result.exit_code == 0
    assert result.output.startswith("<system-reminder>")
    assert result.output.strip().endswith("</system-reminder>")


# ---------------------------------------------------------------------------
# pkm hook setup (non-destructive registration)
# ---------------------------------------------------------------------------


def test_hook_setup_dry_run_claude_code(runner, vault_env, tmp_path, monkeypatch):
    """setup --tool claude-code --dry-run shows what would be added without writing."""
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(
        main, ["hook", "setup", "--tool", "claude-code", "--dry-run"]
    )
    assert result.exit_code == 0
    assert "SessionStart" in result.output
    assert "Dry run" in result.output
    assert "pkm agent hook" not in result.output
    # dry-run must not write settings.json
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_hook_setup_claude_code_writes_settings(
    runner, vault_env, tmp_path, monkeypatch
):
    """pkm hook setup --tool claude-code merges PKM hooks into ~/.claude/settings.json."""
    monkeypatch.setenv("HOME", str(tmp_path))

    result = runner.invoke(main, ["hook", "setup", "--tool", "claude-code"])
    assert result.exit_code == 0, result.output

    settings = tmp_path / "home" / ".claude" / "settings.json"
    assert settings.exists(), "setup must write settings.json"
    data = json.loads(settings.read_text())
    assert "SessionStart" in data["hooks"]
    assert "pkm hook remove" in result.output


def test_hook_setup_idempotent(runner, vault_env, tmp_path, monkeypatch):
    """Running hook setup twice skips already-installed hooks."""
    monkeypatch.setenv("HOME", str(tmp_path))

    result1 = runner.invoke(main, ["hook", "setup", "--tool", "claude-code"])
    result2 = runner.invoke(main, ["hook", "setup", "--tool", "claude-code"])

    assert result1.exit_code == 0, result1.output
    assert result2.exit_code == 0, result2.output
    assert "Added hook" in result1.output
    assert (
        "Already installed" in result2.output
        or "nothing to do" in result2.output.lower()
    )


# ---------------------------------------------------------------------------
# Local mock_model fixture for test_hooks
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_model(monkeypatch):
    """Replace SentenceTransformer with a deterministic fake model."""
    import numpy as np

    class FakeModel:
        def encode(self, texts, **kwargs):
            texts_list = texts if isinstance(texts, list) else [texts]
            return np.array([[hash(t) % 100 / 100.0] * 384 for t in texts_list])

    monkeypatch.setattr(
        "pkm.search_engine._require_transformers", lambda name: FakeModel()
    )


# ---------------------------------------------------------------------------
# GAP 3: turn-start stdin dynamic injection
# ---------------------------------------------------------------------------


def test_turn_start_with_stdin_prompt_injects_notes(
    runner, vault_env, tmp_vault, monkeypatch, mock_model
):
    """When stdin has a prompt, relevant notes are searched and injected."""
    import json as _json
    from pkm.search_engine import SearchResult, build_index

    build_index(tmp_vault)

    def fake_search(query, index, **kwargs):
        return [
            SearchResult(
                note_id="mvcc-note",
                title="MVCC Concurrency",
                score=0.9,
                backlink_count=1,
                tags=["database"],
                rank=1,
                memory_type="semantic",
                importance=8.0,
                path="",
            )
        ]

    monkeypatch.setattr("pkm.search_engine.search", fake_search)

    payload = _json.dumps(
        {"hook_event_name": "UserPromptSubmit", "prompt": "MVCC database isolation"}
    )
    result = runner.invoke(
        main,
        ["hook", "run", "turn-start", "--format", "plain"],
        input=payload,
    )
    assert result.exit_code == 0
    assert (
        "Relevant Notes" in result.output
        or "MVCC" in result.output
        or "pkm search" in result.output
    )


def test_turn_start_no_stdin_shows_advisory(runner, vault_env):
    """Without stdin, turn-start shows advisory text normally."""
    result = runner.invoke(main, ["hook", "run", "turn-start", "--format", "plain"])
    assert result.exit_code == 0
    assert "pkm search" in result.output


# ---------------------------------------------------------------------------
# GAP 4: session-start consolidation trigger
# ---------------------------------------------------------------------------


def test_session_start_increments_session_count(runner, vault_env, tmp_vault):
    """Session-start increments session_count in .pkm/session_state.json."""
    import json as _json

    runner.invoke(main, ["hook", "run", "session-start"])
    state_path = tmp_vault.pkm_dir / "session_state.json"
    assert state_path.exists()
    state = _json.loads(state_path.read_text())
    assert state["session_count"] >= 1


def test_consolidation_trigger_after_threshold(runner, vault_env, tmp_vault):
    """After sessions reach threshold with unconsolidated daily notes, consolidation message appears."""
    import json as _json
    from datetime import timedelta

    # Create unconsolidated daily notes
    for i in range(1, 4):
        d = (date.today() - timedelta(days=i)).isoformat()
        (tmp_vault.daily_dir / f"{d}.md").write_text(
            f"---\nid: {d}\ntags: []\n---\n- entry\n", encoding="utf-8"
        )

    # Enable auto_trigger via config with low threshold
    config_path = tmp_vault.pkm_dir / "config.toml"
    config_path.write_text(
        "[consolidation]\nauto_trigger = true\nsession_threshold = 5\ncooldown_hours = 24\n"
    )

    # Set session_count to 4 (one below threshold so next invoke hits 5)
    state_path = tmp_vault.pkm_dir / "session_state.json"
    state_path.write_text(
        _json.dumps({"session_count": 4, "last_consolidation_at": None})
    )

    result = runner.invoke(main, ["hook", "run", "session-start"])
    assert result.exit_code == 0
    assert (
        "Consolidation Recommended" in result.output
        or "consolidat" in result.output.lower()
    )


def test_consolidation_cooldown_suppresses_trigger(runner, vault_env, tmp_vault):
    """If last_consolidation_at is within cooldown window, no trigger message."""
    import json as _json
    from datetime import datetime, timezone, timedelta

    config_path = tmp_vault.pkm_dir / "config.toml"
    config_path.write_text(
        "[consolidation]\nauto_trigger = true\nsession_threshold = 2\ncooldown_hours = 24\n"
    )

    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    state_path = tmp_vault.pkm_dir / "session_state.json"
    state_path.write_text(
        _json.dumps({"session_count": 5, "last_consolidation_at": recent})
    )

    result = runner.invoke(main, ["hook", "run", "session-start"])
    assert result.exit_code == 0
    assert "Consolidation Recommended" not in result.output


def test_corrupt_session_state_recovery(runner, vault_env, tmp_vault):
    """Corrupt session_state.json is reset to defaults, no crash."""
    state_path = tmp_vault.pkm_dir / "session_state.json"
    state_path.write_text("{{invalid json{{", encoding="utf-8")
    result = runner.invoke(main, ["hook", "run", "session-start"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# _tail_daily_entries — recent context continuity
# ---------------------------------------------------------------------------


def test_tail_daily_entries_today_only(tmp_vault):
    """When today has enough entries, only today's entries are returned."""
    from pkm.commands.hook import _tail_daily_entries

    today = date.today().isoformat()
    (tmp_vault.daily_dir / f"{today}.md").write_text(
        "---\nid: today\ntags: []\n---\n"
        "- [08:00] entry one\n"
        "- [09:00] entry two\n"
        "- [10:00] entry three\n"
        "- [11:00] entry four\n"
        "- [12:00] entry five\n"
        "- [13:00] entry six\n",
        encoding="utf-8",
    )

    result = _tail_daily_entries(tmp_vault, total=5)
    # Should have date header + 5 entries (last 5)
    assert result[0] == f"### {today}"
    assert len(result) == 6  # 1 header + 5 entries
    assert "entry two" in result[1]
    assert "entry six" in result[-1]


def test_tail_daily_entries_backfill_from_yesterday(tmp_vault):
    """When today has fewer entries than total, backfill from yesterday."""
    from pkm.commands.hook import _tail_daily_entries

    today = date.today()
    yesterday = today - timedelta(days=1)

    (tmp_vault.daily_dir / f"{today.isoformat()}.md").write_text(
        "---\nid: today\ntags: []\n---\n"
        "- [10:00] today entry one\n"
        "- [11:00] today entry two\n",
        encoding="utf-8",
    )
    (tmp_vault.daily_dir / f"{yesterday.isoformat()}.md").write_text(
        "---\nid: yesterday\ntags: []\n---\n"
        "- [08:00] yesterday entry one\n"
        "- [09:00] yesterday entry two\n"
        "- [20:00] yesterday entry three\n"
        "- [21:00] yesterday entry four\n"
        "- [22:00] yesterday entry five\n",
        encoding="utf-8",
    )

    result = _tail_daily_entries(tmp_vault, total=5)
    # 2 from today + 3 backfill from yesterday = 5 entries + 2 headers
    assert f"### {yesterday.isoformat()}" in result
    assert f"### {today.isoformat()}" in result
    assert sum(1 for line in result if line.startswith("- [")) == 5
    # Yesterday entries should be the last 3
    assert "yesterday entry three" in result[1]
    assert "yesterday entry five" in result[3]
    # Today entries follow
    assert "today entry one" in result[5]
    assert "today entry two" in result[6]


def test_tail_daily_entries_empty_daily(tmp_vault):
    """When no daily notes exist, returns empty list."""
    from pkm.commands.hook import _tail_daily_entries

    result = _tail_daily_entries(tmp_vault, total=5)
    assert result == []


def test_tail_daily_entries_skips_non_entries(tmp_vault):
    """Lines like ## TODO or plain text are not treated as entries."""
    from pkm.commands.hook import _tail_daily_entries

    today = date.today().isoformat()
    (tmp_vault.daily_dir / f"{today}.md").write_text(
        "---\nid: today\ntags: []\n---\n"
        "- [08:00] real entry\n"
        "## TODO\n"
        "- plain bullet without timestamp\n"
        "some plain text\n",
        encoding="utf-8",
    )

    result = _tail_daily_entries(tmp_vault, total=5)
    assert len(result) == 2  # 1 header + 1 entry
    assert "real entry" in result[1]


def test_turn_start_includes_recent_context(runner, vault_env, tmp_vault):
    """turn-start hook output includes Recent Context section from daily entries."""
    today = date.today().isoformat()
    (tmp_vault.daily_dir / f"{today}.md").write_text(
        "---\nid: today\ntags: []\n---\n"
        "- [09:00] context entry alpha\n"
        "- [10:00] context entry beta\n",
        encoding="utf-8",
    )
    result = runner.invoke(main, ["hook", "run", "turn-start", "--format", "plain"])
    assert result.exit_code == 0
    assert "## Recent Context" in result.output
    assert "context entry alpha" in result.output
    assert "context entry beta" in result.output


def test_turn_start_config_daily_tail_n(runner, vault_env, tmp_vault):
    """hooks.daily_tail_n in config.toml controls how many daily entries are shown."""
    today = date.today().isoformat()
    (tmp_vault.daily_dir / f"{today}.md").write_text(
        "---\nid: today\ntags: []\n---\n"
        + "".join(f"- [{h:02d}:00] entry {h}\n" for h in range(10)),
        encoding="utf-8",
    )
    # Set daily_tail_n = 2 via config
    tmp_vault.pkm_dir.mkdir(parents=True, exist_ok=True)
    (tmp_vault.pkm_dir / "config.toml").write_text(
        "[hooks]\ndaily_tail_n = 2\n", encoding="utf-8"
    )
    result = runner.invoke(main, ["hook", "run", "turn-start", "--format", "plain"])
    assert result.exit_code == 0
    # Only last 2 entries (08, 09) should appear
    assert "entry 9" in result.output
    assert "entry 8" in result.output
    assert "entry 0" not in result.output
