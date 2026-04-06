"""Tests for git vault naming and migration in pkm.config."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pkm.config import (
    VaultConfig,
    _find_git_root,
    discover_vaults,
    ensure_vault_exists,
    get_git_vault_name,
)


def test_parse_https_remote(tmp_path, monkeypatch):
    """get_git_vault_name parses https remote URL into @owner--repo format."""
    monkeypatch.setattr("pkm.config._find_git_root", lambda: tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "https://github.com/taeho/pkm.git\n"

    with patch("subprocess.run", return_value=mock_result):
        name = get_git_vault_name()

    assert name == "@taeho--pkm"


def test_parse_ssh_remote(tmp_path, monkeypatch):
    """get_git_vault_name parses SSH remote URL into @owner--repo format."""
    monkeypatch.setattr("pkm.config._find_git_root", lambda: tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "git@github.com:taeho/pkm.git\n"

    with patch("subprocess.run", return_value=mock_result):
        name = get_git_vault_name()

    assert name == "@taeho--pkm"


def test_parse_no_remote(tmp_path, monkeypatch):
    """get_git_vault_name falls back to @{basename} when git remote fails."""
    monkeypatch.setattr("pkm.config._find_git_root", lambda: tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""

    with patch("subprocess.run", return_value=mock_result):
        name = get_git_vault_name()

    assert name == f"@{tmp_path.name}"


def test_vault_migration_renames_dir(tmp_path, monkeypatch):
    """ensure_vault_exists renames old vault directory to new name."""
    monkeypatch.setattr("pkm.config.get_vaults_root", lambda: tmp_path)
    monkeypatch.setattr("pkm.config.load_config", lambda: {})
    monkeypatch.setattr("pkm.config.save_config", lambda d: None)

    old_vault = tmp_path / "pkm"
    old_vault.mkdir()
    (old_vault / "notes").mkdir()

    ensure_vault_exists("@taeho--pkm", old_name="pkm")

    assert (tmp_path / "@taeho--pkm").exists()
    assert not old_vault.exists()


def test_vault_migration_updates_config(tmp_path, monkeypatch):
    """ensure_vault_exists updates config vault reference after migration."""
    monkeypatch.setattr("pkm.config.get_vaults_root", lambda: tmp_path)

    saved = {}

    def fake_load_config():
        return {"defaults": {"vault": "pkm"}}

    def fake_save_config(data):
        saved.update(data)

    monkeypatch.setattr("pkm.config.load_config", fake_load_config)
    monkeypatch.setattr("pkm.config.save_config", fake_save_config)

    old_vault = tmp_path / "pkm"
    old_vault.mkdir()
    (old_vault / "notes").mkdir()

    ensure_vault_exists("@taeho--pkm", old_name="pkm")

    assert saved.get("defaults", {}).get("vault") == "@taeho--pkm"


def test_discover_vaults_includes_at_prefix(tmp_path, monkeypatch):
    """discover_vaults finds @-prefixed vault directories."""
    monkeypatch.setattr("pkm.config.get_vaults_root", lambda: tmp_path)

    at_vault = tmp_path / "@taeho--pkm"
    at_vault.mkdir()
    (at_vault / "notes").mkdir()

    vaults = discover_vaults(root=tmp_path)

    assert "@taeho--pkm" in vaults
    assert vaults["@taeho--pkm"].path == at_vault
