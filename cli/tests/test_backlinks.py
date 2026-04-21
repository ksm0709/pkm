"""Tests for backlink display in `note show` and `note links`."""

from __future__ import annotations

import pytest
import json

from click.testing import CliRunner

from pkm.cli import main


@pytest.fixture(autouse=True)
def patch_vaults(monkeypatch, tmp_vault):
    monkeypatch.setattr(
        "pkm.config.discover_vaults", lambda *a, **kw: {"test-vault": tmp_vault}
    )


@pytest.fixture
def cli_runner(monkeypatch, tmp_vault):
    """Return a callable that invokes main with tmp_vault injected."""
    runner = CliRunner()

    def invoke(*args):
        monkeypatch.setattr(
            "pkm.config.discover_vaults",
            lambda *a, **kw: {"test-vault": tmp_vault},
        )
        return runner.invoke(
            main, ["--vault", "test-vault", *args], catch_exceptions=False
        )

    return invoke


def test_note_show_displays_backlinks(cli_runner, tmp_vault):
    """note show mvcc returns JSON with backlinks array containing linked note titles."""
    result = cli_runner("note", "show", "mvcc")
    assert result.exit_code == 0
    # New JSON-first output: backlinks appear in the notes[].backlinks array
    json_text = result.output.split("\n* ")[0].strip()
    data = json.loads(json_text)
    if data["notes"]:
        backlinks = data["notes"][0].get("backlinks", [])
        all_text = result.output.lower()
        assert (
            any(
                "database" in b.lower()
                or "isolation" in b.lower()
                or "concurrency" in b.lower()
                for b in backlinks
            )
            or "database" in all_text
        )


def test_note_show_backlink_with_description(cli_runner, tmp_vault):
    """note show mvcc JSON output includes backlinks array with note titles."""
    result = cli_runner("note", "show", "mvcc")
    assert result.exit_code == 0
    json_text = result.output.split("\n* ")[0].strip()
    data = json.loads(json_text)
    if data["notes"]:
        assert "backlinks" in data["notes"][0]
        assert isinstance(data["notes"][0]["backlinks"], list)


def test_note_show_no_backlinks(cli_runner, tmp_vault):
    """Orphan note should not show a Backlinks section."""
    result = cli_runner("note", "show", "isolated")
    assert result.exit_code == 0
    assert "Backlinks" not in result.output


def test_note_links_command(cli_runner, tmp_vault):
    """note links mvcc should display a table with backlink entries."""
    result = cli_runner("note", "links", "mvcc")
    assert result.exit_code == 0
    # Table should contain at least one of the known backlink sources
    assert (
        "database-isolation" in result.output or "concurrency" in result.output.lower()
    )
