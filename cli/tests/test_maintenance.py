"""Tests for maintenance commands: tags, stats, stale."""

from __future__ import annotations

import json
import os
import time

import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig


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
    assert "orphans" in data
    assert data["index"] == "not indexed"


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


def test_stale_no_results(cli_runner):
    # Very large days threshold — nothing should be stale
    result = cli_runner("note", "stale", "--days", "9999")
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["count"] == 0
