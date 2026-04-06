"""Tests for backlink display in `note show` and `note links`."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from pkm.cli import main


@pytest.fixture(autouse=True)
def patch_vaults(monkeypatch, tmp_vault):
    monkeypatch.setattr("pkm.config.discover_vaults", lambda *a, **kw: {"test-vault": tmp_vault})


@pytest.fixture
def cli_runner(monkeypatch, tmp_vault):
    """Return a callable that invokes main with tmp_vault injected."""
    runner = CliRunner()

    def invoke(*args):
        monkeypatch.setattr(
            "pkm.config.discover_vaults",
            lambda *a, **kw: {"test-vault": tmp_vault},
        )
        return runner.invoke(main, ["--vault", "test-vault", *args], catch_exceptions=False)

    return invoke


def test_note_show_displays_backlinks(cli_runner, tmp_vault):
    """note show mvcc should show a Backlinks section listing database-isolation."""
    result = cli_runner("note", "show", "mvcc")
    assert result.exit_code == 0
    assert "Backlinks" in result.output
    assert "database-isolation" in result.output.lower() or "database" in result.output.lower()


def test_note_show_backlink_with_description(cli_runner, tmp_vault):
    """note show mvcc should include concurrency-note's description."""
    result = cli_runner("note", "show", "mvcc")
    assert result.exit_code == 0
    assert "동시성 제어 기법 비교 노트" in result.output


def test_note_show_no_backlinks(cli_runner, tmp_vault):
    """Orphan note should not show a Backlinks section."""
    result = cli_runner("note", "show", "고립된")
    assert result.exit_code == 0
    assert "Backlinks" not in result.output


def test_note_links_command(cli_runner, tmp_vault):
    """note links mvcc should display a table with backlink entries."""
    result = cli_runner("note", "links", "mvcc")
    assert result.exit_code == 0
    # Table should contain at least one of the known backlink sources
    assert "database-isolation" in result.output or "concurrency" in result.output.lower()
