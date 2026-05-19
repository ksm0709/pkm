"""Tests for tools/maintenance.py — vault_stats, list_stale_notes, list_orphans."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path


from pkm.tools.maintenance import (
    list_malformed_notes,
    list_orphans,
    list_stale_notes,
    vault_stats,
)


def _run(coro):
    """Run an async tool coroutine synchronously."""
    return asyncio.run(coro)


def test_vault_stats_returns_expected_keys(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(vault_stats()))
    assert {
        "notes",
        "dailies",
        "orphans",
        "unique_tags",
        "avg_links_per_note",
        "index",
    } <= result.keys()


def test_vault_stats_note_count(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(vault_stats()))
    assert result["notes"] >= 4  # fixture has ≥4 notes


def test_vault_stats_orphan_count(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(vault_stats()))
    assert result["orphans"] >= 1  # isolated-note.md is an orphan


def test_vault_stats_empty_vault(monkeypatch, tmp_path):
    vault_path = tmp_path / "empty-vault"
    for d in ("notes", "daily", "tags", "tasks", ".pkm"):
        (vault_path / d).mkdir(parents=True)
    monkeypatch.setenv("PKM_VAULT_DIR", str(vault_path))
    result = json.loads(_run(vault_stats()))
    assert result["notes"] == 0
    assert result["orphans"] == 0


def test_list_orphans_finds_isolated_note(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_orphans()))
    filenames = [o["filename"] for o in result["orphans"]]
    assert "isolated-note.md" in filenames


def test_list_orphans_count_field(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_orphans()))
    assert result["count"] == len(result["orphans"])


def test_list_orphans_has_tags_field(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_orphans()))
    for o in result["orphans"]:
        assert "tags" in o
        assert isinstance(o["tags"], list)


def test_list_malformed_notes_finds_duplicate_frontmatter(tmp_vault, monkeypatch):
    malformed = tmp_vault.notes_dir / "duplicate-frontmatter.md"
    malformed.write_text(
        "---\n"
        "id: duplicate-frontmatter\n"
        "tags: pkm-webapp\n"
        "---\n\n"
        "---\n"
        "aliases: [duplicate]\n"
        "tags: [logging]\n"
        "---\n\n"
        "# Duplicate metadata\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))

    result = json.loads(_run(list_malformed_notes()))

    assert result["count"] == 1
    assert result["malformed_notes"][0] == {
        "path": "notes/duplicate-frontmatter.md",
        "note_id": "duplicate-frontmatter",
        "issue": "duplicate_leading_frontmatter",
        "repairable": True,
    }


def test_list_malformed_notes_marks_unquoted_colon_title_repairable(
    tmp_vault, monkeypatch
):
    malformed = tmp_vault.notes_dir / "neo-mcp-opencode-오픈소스-에이전트-허브.md"
    malformed.write_text(
        "---\n"
        "id: neo-mcp-opencode-오픈소스-에이전트-허브\n"
        "title: Neo MCP: opencode 오픈소스 에이전트 허브\n"
        "tags: [hub]\n"
        "---\n\n"
        "# Hub\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))

    result = json.loads(_run(list_malformed_notes()))

    assert {
        "path": "notes/neo-mcp-opencode-오픈소스-에이전트-허브.md",
        "note_id": "neo-mcp-opencode-오픈소스-에이전트-허브",
        "issue": "unquoted_frontmatter_scalar",
        "repairable": True,
    } in result["malformed_notes"]


def test_list_malformed_notes_empty_when_clean(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))

    result = json.loads(_run(list_malformed_notes()))

    assert result == {"malformed_notes": [], "count": 0}


def test_get_pkm_tools_exposes_list_malformed_notes_to_ask_agent():
    from pkm.tools import get_pkm_tools

    tool_names = {tool.__name__ for tool in get_pkm_tools()}

    assert "list_malformed_notes" in tool_names
    assert "get_note_neighbors" in tool_names
    assert "create_daily_subnote" in tool_names


def test_list_stale_notes_days_zero_returns_all(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_stale_notes(days=0)))
    assert result["count"] >= 1
    assert result["threshold_days"] == 0


def test_list_stale_notes_far_future_returns_empty(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_stale_notes(days=99999)))
    assert result["count"] == 0
    assert result["stale_notes"] == []


def test_list_stale_notes_structure(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    result = json.loads(_run(list_stale_notes(days=0)))
    for item in result["stale_notes"]:
        assert "note" in item
        assert "last_modified" in item
        assert "days_ago" in item


def test_maintenance_tools_report_command_errors(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    monkeypatch.setattr(
        "pkm.commands.maintenance.compute_vault_stats",
        lambda vault: (_ for _ in ()).throw(RuntimeError("stats failed")),
    )
    assert _run(vault_stats()) == "Error: stats failed"

    monkeypatch.setattr(
        "pkm.commands.maintenance.list_stale",
        lambda vault, days: (_ for _ in ()).throw(RuntimeError("stale failed")),
    )
    assert _run(list_stale_notes()) == "Error: stale failed"

    monkeypatch.setattr(
        "pkm.wikilinks.find_orphans",
        lambda vault: (_ for _ in ()).throw(RuntimeError("orphans failed")),
    )
    assert _run(list_orphans()) == "Error: orphans failed"


def test_list_malformed_notes_reports_unreadable_repair_failure(tmp_vault, monkeypatch):
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_vault.path))
    broken = tmp_vault.notes_dir / "broken-frontmatter.md"
    broken.write_text("---\nid: broken\n---\n\nBody\n", encoding="utf-8")
    original_read_text = Path.read_text

    def fail_broken(self, *args, **kwargs):
        if self == broken:
            raise OSError("cannot read")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_broken)

    result = json.loads(_run(list_malformed_notes()))
    assert result["malformed_notes"] == [
        {
            "path": "notes/broken-frontmatter.md",
            "note_id": "broken-frontmatter",
            "issue": "frontmatter_parse_error",
            "repairable": False,
        }
    ]
