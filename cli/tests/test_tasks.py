"""Tests for task extraction logic and create_daily_subnote tool."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path


from pkm.config import VaultConfig
from pkm.tasks import (
    _detect_status,
    _parse_tasks_from_text,
    _section_owner_matches,
    extract_tasks,
)


def _make_vault(tmp_path: Path) -> VaultConfig:
    vault_path = tmp_path / "vault"
    for d in ("daily", "notes", ".pkm"):
        (vault_path / d).mkdir(parents=True)
    return VaultConfig(name="vault", path=vault_path)


def _write_daily(vault: VaultConfig, date_str: str, content: str) -> Path:
    path = vault.daily_dir / f"{date_str}.md"
    path.write_text(content, encoding="utf-8")
    return path


def _default_statuses() -> dict:
    return {
        "todo": ["TODO", "[ ]"],
        "wip": ["WIP", "[>]"],
        "done": ["DONE", "[x]"],
        "cancel": ["CANCEL", "[-]"],
    }


# ---------------------------------------------------------------------------
# VaultConfig defaults
# ---------------------------------------------------------------------------


def test_vaultconfig_task_statuses_defaults(tmp_path):
    vault = VaultConfig(name="v", path=tmp_path)
    assert "todo" in vault.task_statuses
    assert "wip" in vault.task_statuses
    assert "done" in vault.task_statuses
    assert "cancel" in vault.task_statuses


def test_vaultconfig_task_assignee_patterns_default_empty(tmp_path):
    vault = VaultConfig(name="v", path=tmp_path)
    assert vault.task_assignee_patterns == []


# ---------------------------------------------------------------------------
# _detect_status
# ---------------------------------------------------------------------------


def test_detect_status_checkbox_todo():
    assert _detect_status("- [ ] buy milk", _default_statuses()) == "todo"


def test_detect_status_checkbox_wip():
    assert _detect_status("- [>] working on PR", _default_statuses()) == "wip"


def test_detect_status_checkbox_done():
    assert _detect_status("- [x] merged", _default_statuses()) == "done"


def test_detect_status_checkbox_cancel():
    assert _detect_status("- [-] cancelled", _default_statuses()) == "cancel"


def test_detect_status_inline_tag_todo():
    assert _detect_status("- fix the bug #TODO", _default_statuses()) == "todo"


def test_detect_status_inline_tag_wip():
    assert _detect_status("- PR open #WIP", _default_statuses()) == "wip"


def test_detect_status_inline_tag_done():
    assert _detect_status("- deployed #DONE", _default_statuses()) == "done"


def test_detect_status_checkbox_priority_over_tag():
    # checkbox takes priority over inline tag
    assert _detect_status("- [x] item #TODO", _default_statuses()) == "done"


def test_detect_status_none():
    assert _detect_status("- plain bullet", _default_statuses()) is None


# ---------------------------------------------------------------------------
# _section_owner_matches
# ---------------------------------------------------------------------------


def test_section_owner_matches_hit():
    assert _section_owner_matches("## Release #TaehoKang", ["Taeho"]) is True


def test_section_owner_matches_miss():
    assert _section_owner_matches("## Release #JunhoOh", ["Taeho"]) is False


def test_section_owner_no_tag():
    assert _section_owner_matches("## General Tasks", ["Taeho"]) is None


def test_section_owner_case_insensitive():
    assert _section_owner_matches("## Sprint #taehokang", ["TaehoKang"]) is True


# ---------------------------------------------------------------------------
# _parse_tasks_from_text (unit tests — no date mocking needed)
# ---------------------------------------------------------------------------


def test_parse_tasks_checkbox():
    content = "## TODO\n- [ ] task A\n- [>] task B\n- [x] task C\n"
    result = _parse_tasks_from_text(content, _default_statuses(), [])
    assert "task A" in result["todo"]
    assert "task B" in result["wip"]
    assert "task C" in result["done"]


def test_parse_tasks_inline_tags():
    content = "## TODO\n- fix login #TODO\n- deploy #DONE\n"
    result = _parse_tasks_from_text(content, _default_statuses(), [])
    assert any("fix login" in t for t in result["todo"])
    assert any("deploy" in t for t in result["done"])


def test_parse_tasks_assignee_filter_hit():
    content = (
        "## Sprint #TaehoKang\n- [ ] my task\n## Sprint #JunhoOh\n- [ ] other task\n"
    )
    result = _parse_tasks_from_text(content, _default_statuses(), ["Taeho"])
    assert any("my task" in t for t in result["todo"])
    assert not any("other task" in t for t in result["todo"])


def test_parse_tasks_no_filter_includes_all():
    content = (
        "## Sprint #TaehoKang\n- [ ] my task\n## Sprint #JunhoOh\n- [ ] other task\n"
    )
    result = _parse_tasks_from_text(content, _default_statuses(), [])
    assert any("my task" in t for t in result["todo"])
    assert any("other task" in t for t in result["todo"])


def test_parse_tasks_no_owner_section_always_included():
    content = "## General\n- [ ] public task\n"
    result = _parse_tasks_from_text(content, _default_statuses(), ["Taeho"])
    assert any("public task" in t for t in result["todo"])


def test_parse_tasks_cancel_status():
    content = "- [-] dropped item\n"
    result = _parse_tasks_from_text(content, _default_statuses(), [])
    assert any("dropped item" in t for t in result["cancel"])


def test_parse_tasks_empty_text():
    result = _parse_tasks_from_text("", _default_statuses(), [])
    for items in result.values():
        assert items == []


def test_parse_tasks_no_task_lines():
    content = "# Header\nSome prose here.\nAnother line.\n"
    result = _parse_tasks_from_text(content, _default_statuses(), [])
    for items in result.values():
        assert items == []


# ---------------------------------------------------------------------------
# extract_tasks integration tests (write today's actual date files)
# ---------------------------------------------------------------------------


def test_extract_tasks_reads_todays_file(tmp_path):
    vault = _make_vault(tmp_path)
    today = datetime.now().strftime("%Y-%m-%d")
    _write_daily(vault, today, "- [ ] integration task\n")
    result = extract_tasks(vault, scan_days=1)
    assert any("integration task" in t for t in result["todo"])


def test_extract_tasks_scans_subnotes(tmp_path):
    vault = _make_vault(tmp_path)
    today = datetime.now().strftime("%Y-%m-%d")
    _write_daily(vault, today, "- [ ] main note task\n")
    subnote = vault.daily_dir / f"{today}-standup.md"
    subnote.write_text("- [>] subnote task\n", encoding="utf-8")
    result = extract_tasks(vault, scan_days=1)
    assert any("main note task" in t for t in result["todo"])
    assert any("subnote task" in t for t in result["wip"])


def test_extract_tasks_missing_daily_dir(tmp_path):
    # daily_dir does not exist — should return empty dicts without crashing
    vault = VaultConfig(name="v", path=tmp_path / "nonexistent")
    result = extract_tasks(vault, scan_days=1)
    for items in result.values():
        assert items == []


# ---------------------------------------------------------------------------
# create_daily_subnote @tool
# ---------------------------------------------------------------------------


def test_create_daily_subnote_tool(tmp_path, monkeypatch):
    vault = _make_vault(tmp_path)
    monkeypatch.setenv("PKM_VAULT_DIR", str(vault.path))

    from pkm.tools.daily import create_daily_subnote

    result = asyncio.run(
        create_daily_subnote(title="test-summary", content="## WIP\n- [>] task1\n")
    )
    assert "test-summary" in result

    # Subnote file exists
    today = datetime.now().strftime("%Y-%m-%d")
    subnote = vault.daily_dir / f"{today}-test-summary.md"
    assert subnote.exists()

    # Daily note has wikilink to subnote
    daily = vault.daily_dir / f"{today}.md"
    assert daily.exists()
    content = daily.read_text()
    assert "test-summary" in content


def test_create_daily_subnote_empty_title(tmp_path, monkeypatch):
    vault = _make_vault(tmp_path)
    monkeypatch.setenv("PKM_VAULT_DIR", str(vault.path))

    from pkm.tools.daily import create_daily_subnote

    result = asyncio.run(create_daily_subnote(title="", content="some content"))
    assert "Error" in result or "error" in result.lower()


def test_create_daily_subnote_idempotent(tmp_path, monkeypatch):
    """Calling twice with same title does not overwrite existing subnote."""
    vault = _make_vault(tmp_path)
    monkeypatch.setenv("PKM_VAULT_DIR", str(vault.path))

    from pkm.tools.daily import create_daily_subnote

    asyncio.run(
        create_daily_subnote(title="idempotent-note", content="original content\n")
    )
    asyncio.run(create_daily_subnote(title="idempotent-note", content="new content\n"))

    today = datetime.now().strftime("%Y-%m-%d")
    subnote = vault.daily_dir / f"{today}-idempotent-note.md"
    text = subnote.read_text()
    assert "original content" in text
    assert "new content" not in text
