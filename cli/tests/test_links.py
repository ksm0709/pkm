"""CLI integration tests for link commands."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cli_runner(runner, tmp_vault: VaultConfig, monkeypatch):
    """Return a runner that invokes main with tmp_vault injected."""

    def invoke(*args):
        monkeypatch.setattr(
            "pkm.config.discover_vaults",
            lambda root=None: {"test-vault": tmp_vault},
        )
        monkeypatch.setattr("pkm.config.load_config", lambda: {})
        return runner.invoke(main, list(args), catch_exceptions=False)

    return invoke


def test_orphans_command(cli_runner, tmp_vault: VaultConfig):
    result = cli_runner("orphans")
    assert result.exit_code == 0
    # Both orphan notes should appear in output
    assert "고립된-노트.md" in result.output
    assert "untagged-note.md" in result.output
    # Count line should appear
    assert "orphan" in result.output.lower()
