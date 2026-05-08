"""Tests for maintenance commands: tags, stats, stale."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

import pkm.commands.maintenance as maintenance_mod
from pkm.cli import main
from pkm.config import VaultConfig
from pkm.commands.maintenance import compute_vault_stats, list_stale


@pytest.fixture
def cli_runner(tmp_vault: VaultConfig, monkeypatch):
    monkeypatch.setattr(
        "pkm.config.discover_vaults",
        lambda root=None: {tmp_vault.name: tmp_vault},
    )
    runner = CliRunner()

    def invoke(*args):
        return runner.invoke(main, ["--vault", tmp_vault.name, *args])

    return invoke


def test_tags_command(cli_runner):
    result = cli_runner("tags")
    assert result.exit_code == 0
    data = json.loads(result.output)
    tag_names = [t["tag"] for t in data["tags"]]
    assert "database" in tag_names
    assert "daily-notes" in tag_names


def test_stats_command(cli_runner):
    result = cli_runner("stats")
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "notes" in data
    assert "dailies" in data
    assert "tasks" in data
    assert "orphans" in data
    assert data["index"] == "not indexed"


def test_compute_vault_stats_counts_tasks_and_ignores_bad_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Vault stats count health signals while tolerating malformed notes and links."""
    vault_path = tmp_path / "stats-vault"
    for dirname in ("notes", "daily", "tasks/archive", ".pkm"):
        (vault_path / dirname).mkdir(parents=True)
    vault = VaultConfig(name="stats-vault", path=vault_path)

    good_note = vault.notes_dir / "good.md"
    bad_note = vault.notes_dir / "bad.md"
    good_note.write_text(
        "---\nid: good\ntags:\n  - research\n---\n\nRelated: [[daily]]\n",
        encoding="utf-8",
    )
    bad_note.write_text(
        "---\nid: bad\ntags: [broken\n---\n\nBad note\n", encoding="utf-8"
    )
    (vault.daily_dir / "2026-05-08.md").write_text(
        "---\nid: 2026-05-08\ntags:\n  - daily-notes\n---\n\nDaily\n",
        encoding="utf-8",
    )
    (vault.path / "tasks" / "ongoing.md").write_text("tasks", encoding="utf-8")
    (vault.path / "tasks" / "archive" / "done.md").write_text(
        "archived tasks", encoding="utf-8"
    )
    index_path = vault.pkm_dir / "index.json"
    index_path.write_text("{}", encoding="utf-8")
    fixed_time = datetime(2026, 5, 8, 9, 30).timestamp()
    os.utime(index_path, (fixed_time, fixed_time))

    original_parse = maintenance_mod.parse
    original_extract_links = maintenance_mod.extract_links

    def parse_with_failure(path: Path):
        if path == bad_note:
            raise ValueError("bad frontmatter")
        return original_parse(path)

    def extract_links_with_failure(text: str):
        if "Bad note" in text:
            raise RuntimeError("cannot parse links")
        return original_extract_links(text)

    monkeypatch.setattr(maintenance_mod, "find_orphans", lambda _vault: [])
    monkeypatch.setattr(maintenance_mod, "parse", parse_with_failure)
    monkeypatch.setattr(maintenance_mod, "extract_links", extract_links_with_failure)

    data = compute_vault_stats(vault)

    assert data["notes"] == 2
    assert data["dailies"] == 1
    assert data["tasks"] == 2
    assert data["orphans"] == 0
    assert data["unique_tags"] == 2
    assert data["avg_links_per_note"] == 0.5
    assert data["index"].startswith("indexed (2026-05-08 09:30")


def test_stats_table_command_includes_all_metrics(cli_runner):
    """Table stats renders the same health metrics as JSON without crashing."""
    result = cli_runner("stats", "--format", "table")

    assert result.exit_code == 0, result.output
    assert "Vault Stats" in result.output
    for label in (
        "Notes",
        "Dailies",
        "Tasks",
        "Orphans",
        "Unique tags",
        "Avg links/note",
        "Index",
    ):
        assert label in result.output


def test_stale_with_old_note(cli_runner, tmp_vault: VaultConfig):
    # Set one note to be 60 days old
    old_note = tmp_vault.notes_dir / "isolated-note.md"
    old_time = time.time() - 60 * 86400
    os.utime(old_note, (old_time, old_time))

    result = cli_runner("note", "stale", "--days", "30")
    assert result.exit_code == 0
    data = json.loads(result.output)
    note_names = [n["note"] for n in data["stale_notes"]]
    assert "isolated-note.md" in note_names


def test_stale_table_lists_old_notes(cli_runner, tmp_vault: VaultConfig):
    """Table stale output gives operators the old note and count summary."""
    old_note = tmp_vault.notes_dir / "isolated-note.md"
    old_time = time.time() - 60 * 86400
    os.utime(old_note, (old_time, old_time))

    result = cli_runner("note", "stale", "--days", "30", "--format", "table")

    assert result.exit_code == 0, result.output
    assert "Stale Notes (> 30 days)" in result.output
    assert "isolated-note.md" in result.output
    assert "stale note(s) found" in result.output


def test_stale_no_results(cli_runner):
    # Very large days threshold — nothing should be stale
    result = cli_runner("note", "stale", "--days", "9999")
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["count"] == 0


def test_stale_table_no_results(cli_runner):
    """Table stale output reports zero results without listing note filenames."""
    result = cli_runner("note", "stale", "--days", "9999", "--format", "table")

    assert result.exit_code == 0, result.output
    assert "Stale Notes (> 9999 days)" in result.output
    assert "0 stale note(s) found" in result.output
    assert "isolated-note.md" not in result.output


def test_list_stale_missing_notes_dir_returns_empty(tmp_path: Path) -> None:
    """Partial vaults without a notes directory have no stale note candidates."""
    vault = VaultConfig(name="partial", path=tmp_path / "partial")

    assert list_stale(vault, days=30) == []
