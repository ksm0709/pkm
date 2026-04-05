"""Tests for vault management commands: list, add, remove."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig


def _make_vaults(tmp_path: Path) -> dict[str, VaultConfig]:
    """Create two minimal vaults under tmp_path."""
    vaults = {}
    for name in ("alpha", "beta"):
        p = tmp_path / name
        (p / "daily").mkdir(parents=True)
        (p / "notes").mkdir()
        (p / "notes" / "note1.md").write_text("# note", encoding="utf-8")
        (p / "daily" / "2026-04-01.md").write_text("# daily", encoding="utf-8")
        vaults[name] = VaultConfig(name=name, path=p)
    return vaults


def _patch_vaults(monkeypatch, vaults: dict[str, VaultConfig]) -> None:
    monkeypatch.setattr("pkm.config.discover_vaults", lambda root=None: vaults)
    monkeypatch.setattr("pkm.commands.vault.discover_vaults", lambda root=None: vaults)


# ---------------------------------------------------------------------------
# vault list
# ---------------------------------------------------------------------------

def test_vault_list_shows_table(tmp_path: Path, monkeypatch):
    vaults = _make_vaults(tmp_path)
    _patch_vaults(monkeypatch, vaults)

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "list"])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output
    assert "beta" in result.output


def test_vault_list_shows_counts(tmp_path: Path, monkeypatch):
    vaults = _make_vaults(tmp_path)
    _patch_vaults(monkeypatch, vaults)

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "list"])
    assert result.exit_code == 0
    # Each vault has 1 note and 1 daily
    assert "1" in result.output


def test_vault_list_marks_default(tmp_path: Path, monkeypatch):
    vaults = _make_vaults(tmp_path)
    _patch_vaults(monkeypatch, vaults)
    monkeypatch.setenv("PKM_DEFAULT_VAULT", "beta")

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "list"])
    assert result.exit_code == 0
    assert "★" in result.output


def test_vault_list_empty(monkeypatch):
    monkeypatch.setattr("pkm.config.discover_vaults", lambda root=None: {})
    monkeypatch.setattr("pkm.commands.vault.discover_vaults", lambda root=None: {})

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "list"])
    assert result.exit_code == 0
    assert "pkm vault add" in result.output


# ---------------------------------------------------------------------------
# vault add
# ---------------------------------------------------------------------------

def test_vault_add_creates_structure(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("pkm.commands.vault.get_vaults_root", lambda: tmp_path)

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "add", "mynewvault"])
    assert result.exit_code == 0, result.output

    vault_path = tmp_path / "mynewvault"
    assert (vault_path / "daily").is_dir()
    assert (vault_path / "notes").is_dir()
    assert (vault_path / "tasks").is_dir()
    assert (vault_path / "tasks" / "archive").is_dir()
    assert (vault_path / "data").is_dir()
    assert (vault_path / ".pkm").is_dir()
    assert (vault_path / ".pkm" / "artifacts").is_dir()
    assert (vault_path / "tasks" / "ongoing.md").is_file()


def test_vault_add_ongoing_md_content(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("pkm.commands.vault.get_vaults_root", lambda: tmp_path)

    runner = CliRunner()
    runner.invoke(main, ["vault", "add", "myvault"])

    ongoing = tmp_path / "myvault" / "tasks" / "ongoing.md"
    content = ongoing.read_text(encoding="utf-8")
    assert "myvault-ongoing-tasks" in content
    assert "진행 중인 일" in content
    assert "🔴" in content


def test_vault_add_already_exists(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("pkm.commands.vault.get_vaults_root", lambda: tmp_path)
    (tmp_path / "existing").mkdir()

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "add", "existing"])
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_vault_add_invalid_name(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("pkm.commands.vault.get_vaults_root", lambda: tmp_path)

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "add", "bad/name"])
    assert result.exit_code != 0
    assert "Invalid vault name" in result.output


# ---------------------------------------------------------------------------
# vault remove
# ---------------------------------------------------------------------------

def test_vault_remove_moves_to_trash(tmp_path: Path, monkeypatch):
    vaults = _make_vaults(tmp_path)
    _patch_vaults(monkeypatch, vaults)

    monkeypatch.setattr(
        "pkm.commands.vault.Path.home", lambda: tmp_path / "home"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "remove", "--yes", "alpha"])
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "alpha").exists()


def test_vault_remove_shows_stats(tmp_path: Path, monkeypatch):
    vaults = _make_vaults(tmp_path)
    _patch_vaults(monkeypatch, vaults)

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "remove", "--yes", "alpha"])
    assert result.exit_code == 0, result.output
    assert "note" in result.output or "1" in result.output


def test_vault_remove_shows_trash_path(tmp_path: Path, monkeypatch):
    vaults = _make_vaults(tmp_path)
    _patch_vaults(monkeypatch, vaults)

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "remove", "--yes", "alpha"])
    assert result.exit_code == 0, result.output
    assert "trash" in result.output


def test_vault_remove_confirmation_prompt(tmp_path: Path, monkeypatch):
    vaults = _make_vaults(tmp_path)
    _patch_vaults(monkeypatch, vaults)

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "remove", "alpha"], input="n\n")
    assert result.exit_code != 0
    assert (tmp_path / "alpha").exists()


def test_vault_remove_not_found(tmp_path: Path, monkeypatch):
    vaults = _make_vaults(tmp_path)
    _patch_vaults(monkeypatch, vaults)

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "remove", "--yes", "nonexistent"])
    assert result.exit_code != 0
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# vault open
# ---------------------------------------------------------------------------

def test_vault_open_sets_default(tmp_path: Path, monkeypatch):
    vaults = _make_vaults(tmp_path)
    _patch_vaults(monkeypatch, vaults)

    saved = {}

    def fake_save(data):
        saved.update(data)

    monkeypatch.setattr("pkm.commands.vault.load_config", lambda: {})
    monkeypatch.setattr("pkm.commands.vault.save_config", fake_save)

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "open", "beta"])
    assert result.exit_code == 0, result.output
    assert saved["defaults"]["vault"] == "beta"


def test_vault_open_shows_success(tmp_path: Path, monkeypatch):
    vaults = _make_vaults(tmp_path)
    _patch_vaults(monkeypatch, vaults)

    monkeypatch.setattr("pkm.commands.vault.load_config", lambda: {})
    monkeypatch.setattr("pkm.commands.vault.save_config", lambda d: None)

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "open", "alpha"])
    assert result.exit_code == 0
    assert "alpha" in result.output


def test_vault_open_not_found(tmp_path: Path, monkeypatch):
    vaults = _make_vaults(tmp_path)
    _patch_vaults(monkeypatch, vaults)

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "open", "nonexistent"])
    assert result.exit_code != 0
    assert "not found" in result.output or "nonexistent" in result.output
