"""Tests for maintenance commands: tags, stats, stale."""

from __future__ import annotations

import os
import time

from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig


def _patch_vaults(monkeypatch, vault: VaultConfig):
    monkeypatch.setattr(
        "pkm.config.discover_vaults",
        lambda root=None: {vault.name: vault},
    )


def test_tags_command(tmp_vault: VaultConfig, monkeypatch):
    _patch_vaults(monkeypatch, tmp_vault)
    runner = CliRunner()
    result = runner.invoke(main, ["--vault", tmp_vault.name, "tags"])
    assert result.exit_code == 0
    assert "database" in result.output
    assert "daily-notes" in result.output


def test_stats_command(tmp_vault: VaultConfig, monkeypatch):
    _patch_vaults(monkeypatch, tmp_vault)
    runner = CliRunner()
    result = runner.invoke(main, ["--vault", tmp_vault.name, "stats"])
    assert result.exit_code == 0
    assert "Notes" in result.output
    assert "Dailies" in result.output
    assert "Orphans" in result.output
    assert "not indexed" in result.output


def test_stale_with_old_note(tmp_vault: VaultConfig, monkeypatch):
    _patch_vaults(monkeypatch, tmp_vault)
    # Set one note to be 60 days old
    old_note = tmp_vault.notes_dir / "고립된-노트.md"
    old_time = time.time() - 60 * 86400
    os.utime(old_note, (old_time, old_time))

    runner = CliRunner()
    result = runner.invoke(main, ["--vault", tmp_vault.name, "note", "stale", "--days", "30"])
    assert result.exit_code == 0
    assert "고립된-노트" in result.output


def test_stale_no_results(tmp_vault: VaultConfig, monkeypatch):
    _patch_vaults(monkeypatch, tmp_vault)
    runner = CliRunner()
    # Very large days threshold — nothing should be stale
    result = runner.invoke(main, ["--vault", tmp_vault.name, "note", "stale", "--days", "9999"])
    assert result.exit_code == 0
    assert "0 stale note(s)" in result.output
