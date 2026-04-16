"""Tests for `pkm tags` group, show, and search subcommands."""

from __future__ import annotations

import pytest
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


def test_tags_no_subcommand(cli_runner, tmp_vault):
    """pkm tags with no subcommand shows a tag count table."""
    result = cli_runner("tags")
    assert result.exit_code == 0
    # Tags table should contain known tags
    assert "database" in result.output
    assert "daily-notes" in result.output


def test_tags_show(cli_runner, tmp_vault):
    """pkm tags show database lists notes with the database tag."""
    result = cli_runner("tags", "show", "database")
    assert result.exit_code == 0
    # Should show the tag panel header
    assert "database" in result.output
    # Should list notes tagged database
    assert "mvcc" in result.output.lower() or "2026-04-01-mvcc" in result.output.lower()


def test_tags_show_lazy_creation(cli_runner, tmp_vault):
    """pkm tags show creates a tag note file lazily if it doesn't exist."""
    result = cli_runner("tags", "show", "database")
    assert result.exit_code == 0
    tag_file = tmp_vault.tags_dir / "database.md"
    assert tag_file.exists()


def test_tags_show_existing_content(cli_runner, tmp_vault):
    """pkm tags show preserves existing tag note content."""
    tag_file = tmp_vault.tags_dir / "postgresql.md"
    tag_file.write_text(
        "---\nid: postgresql\naliases: []\ntags: []\n---\n\nPostgreSQL related notes collection.\n",
        encoding="utf-8",
    )
    result = cli_runner("tags", "show", "postgresql")
    assert result.exit_code == 0
    # Existing body content should appear in the panel
    assert "PostgreSQL" in result.output


def test_tags_search_glob(cli_runner, tmp_vault):
    """pkm tags search 'data*' matches notes with database tag."""
    result = cli_runner("tags", "search", "data*")
    assert result.exit_code == 0
    assert (
        "mvcc" in result.output.lower() or "database-isolation" in result.output.lower()
    )


def test_tags_search_and(cli_runner, tmp_vault):
    """pkm tags search 'database+postgresql' only matches the mvcc note."""
    result = cli_runner("tags", "search", "database+postgresql")
    assert result.exit_code == 0
    assert "mvcc" in result.output.lower()
    # database-isolation only has database, not postgresql — should not appear
    assert "database-isolation" not in result.output


def test_tags_search_or(cli_runner, tmp_vault):
    """pkm tags search 'database,untagged' matches notes from both tags."""
    result = cli_runner("tags", "search", "database,untagged")
    assert result.exit_code == 0
    # database tag notes
    assert (
        "mvcc" in result.output.lower() or "database-isolation" in result.output.lower()
    )
    # untagged tag note
    assert "isolated" in result.output


def test_tags_search_no_results(cli_runner, tmp_vault):
    """pkm tags search with unmatched pattern returns empty results."""
    import json

    result = cli_runner("tags", "search", "nonexistent-tag-xyz")
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["count"] == 0
    assert data["results"] == []
