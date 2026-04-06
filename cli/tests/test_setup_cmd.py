"""Tests for pkm setup command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pkm.cli import main


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_setup_help(runner: CliRunner) -> None:
    """pkm setup --help should display usage without error."""
    result = runner.invoke(main, ["setup", "--help"])
    assert result.exit_code == 0
    assert "setup" in result.output.lower()
    assert "wizard" in result.output.lower()


def test_setup_new_vault(tmp_path: Path, runner: CliRunner) -> None:
    """setup creates a new vault when none exist."""
    vaults_root = tmp_path / "vaults"

    with (
        patch("pkm.commands.setup.discover_vaults", return_value={}),
        patch("pkm.commands.setup._load_setup_choices", return_value=None),
        patch("pkm.commands.setup._save_config_merged") as mock_save,
        patch("pkm.commands.setup.init_vault_dirs") as mock_init,
        patch("pkm.commands.setup.subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 0

        result = runner.invoke(
            main,
            ["setup"],
            input="\n\n" + str(vaults_root) + "\nmynotes\n",
            catch_exceptions=False,
        )

    assert result.exit_code == 0, result.output
    assert "Setup complete" in result.output
    mock_init.assert_called_once()
    mock_save.assert_called_once()
    _, kwargs = mock_save.call_args
    assert kwargs["default_vault"] == "mynotes"


def test_setup_existing_vault(tmp_path: Path, runner: CliRunner) -> None:
    """setup detects existing vaults and skips init."""
    from pkm.config import VaultConfig

    vaults_root = tmp_path / "vaults"
    bear_vault = VaultConfig(name="bear", path=vaults_root / "bear")
    taeho_vault = VaultConfig(name="taeho", path=vaults_root / "taeho")
    existing = {"bear": bear_vault, "taeho": taeho_vault}

    with (
        patch("pkm.commands.setup.discover_vaults", return_value=existing),
        patch("pkm.commands.setup._load_setup_choices", return_value=None),
        patch("pkm.commands.setup._save_config_merged") as mock_save,
        patch("pkm.commands.setup.init_vault_dirs") as mock_init,
        patch("pkm.commands.setup.subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 0

        result = runner.invoke(
            main,
            ["setup"],
            # confirm search=yes, dev=no, use default root, accept default vault 'bear'
            input="y\nn\n" + str(vaults_root) + "\nbear\n",
            catch_exceptions=False,
        )

    assert result.exit_code == 0, result.output
    assert "Found existing vaults" in result.output
    assert "bear" in result.output
    assert "taeho" in result.output
    mock_init.assert_not_called()
    mock_save.assert_called_once()
    _, kwargs = mock_save.call_args
    assert kwargs["default_vault"] == "bear"


def test_setup_registers_as_vault_free(runner: CliRunner) -> None:
    """setup command should not require an active vault to run --help."""
    # If setup were not in VAULT_FREE_COMMANDS, --help would still work,
    # but running it without a vault would fail. We verify via VAULT_FREE_COMMANDS directly.
    from pkm.cli import VAULT_FREE_COMMANDS

    assert "setup" in VAULT_FREE_COMMANDS
