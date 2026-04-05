"""Tests for the `pkm note` command group."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig


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


def _parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    # Strip the leading --- and trailing ---
    inner = text.split("---\n", 2)
    return yaml.safe_load(inner[1])


def test_new_creates_note(tmp_vault):
    runner = CliRunner()
    result = runner.invoke(main, ["--vault", "test-vault", "note", "add", "My First Note"], catch_exceptions=False)
    assert result.exit_code == 0

    today = date.today().isoformat()
    expected_filename = f"{today}-my-first-note.md"
    note_path = tmp_vault.notes_dir / expected_filename
    assert note_path.exists(), f"Expected {note_path} to be created"

    meta = _parse_frontmatter(note_path)
    assert meta["id"] == note_path.stem
    assert meta["aliases"] == []
    assert "tags" in meta


def test_new_with_tags(tmp_vault):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--vault", "test-vault", "note", "add", "Tagged Note", "--tags", "python,database"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    today = date.today().isoformat()
    note_path = tmp_vault.notes_dir / f"{today}-tagged-note.md"
    assert note_path.exists()

    meta = _parse_frontmatter(note_path)
    assert "python" in meta["tags"]
    assert "database" in meta["tags"]


def test_new_korean_title(tmp_vault):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--vault", "test-vault", "note", "add", "한글 제목"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    today = date.today().isoformat()
    # Korean slug fallback: spaces replaced by hyphens
    note_path = tmp_vault.notes_dir / f"{today}-한글-제목.md"
    assert note_path.exists(), f"Expected {note_path} to exist. Notes dir: {list(tmp_vault.notes_dir.iterdir())}"


def test_new_refuses_overwrite(tmp_vault):
    runner = CliRunner()
    args = ["--vault", "test-vault", "note", "add", "Duplicate Note"]
    # Create first time
    result = runner.invoke(main, args, catch_exceptions=False)
    assert result.exit_code == 0

    # Try again — should fail
    result = runner.invoke(main, args)
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_new_generates_source(tmp_vault):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--vault", "test-vault", "note", "add", "Source Test"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    today = date.today().isoformat()
    note_path = tmp_vault.notes_dir / f"{today}-source-test.md"
    assert note_path.exists()

    meta = _parse_frontmatter(note_path)
    assert meta["source"] == today


# ---------------------------------------------------------------------------
# _search_notes unit tests
# ---------------------------------------------------------------------------

def test_search_notes_single_match(tmp_vault):
    """_search_notes finds notes by partial title match."""
    from pkm.commands.notes import _search_notes
    matches = _search_notes(tmp_vault, "mvcc")
    assert len(matches) >= 1
    assert any("mvcc" in m.title.lower() for m in matches)


def test_search_notes_no_match(tmp_vault):
    """_search_notes returns empty list for unmatched query."""
    from pkm.commands.notes import _search_notes
    matches = _search_notes(tmp_vault, "zzz-nonexistent-zzz-xyz")
    assert matches == []


def test_search_notes_case_insensitive(tmp_vault):
    """_search_notes is case-insensitive."""
    from pkm.commands.notes import _search_notes
    lower = _search_notes(tmp_vault, "mvcc")
    upper = _search_notes(tmp_vault, "MVCC")
    assert len(lower) == len(upper)


# ---------------------------------------------------------------------------
# pkm note show
# ---------------------------------------------------------------------------

def test_note_show_single_match(cli_runner, tmp_vault):
    """pkm note show <query> with single match prints note content."""
    result = cli_runner("note", "show", "mvcc")
    assert result.exit_code == 0
    # Content from the note file should be present
    assert len(result.output) > 0


def test_note_show_no_match(cli_runner, tmp_vault):
    """pkm note show with no match exits non-zero."""
    result = cli_runner("note", "show", "zzz-nonexistent-zzz-xyz")
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# pkm note edit
# ---------------------------------------------------------------------------

def test_note_edit_single_match(cli_runner, tmp_vault, monkeypatch):
    """pkm note edit opens editor for single matching note."""
    calls = []

    class _FakeProc:
        returncode = 0

    monkeypatch.setattr("pkm.commands.notes.load_config", lambda: {})
    monkeypatch.setattr("pkm.commands.notes.subprocess.run", lambda args, **kw: (_FakeProc(), calls.append(args))[0])

    result = cli_runner("note", "edit", "mvcc")
    assert result.exit_code == 0
    assert len(calls) == 1
    assert "mvcc" in calls[0][-1]


def test_note_edit_no_match(cli_runner, tmp_vault):
    """pkm note edit with no match exits non-zero."""
    result = cli_runner("note", "edit", "zzz-nonexistent-zzz-xyz")
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# pkm note stale / pkm note orphans
# ---------------------------------------------------------------------------

def test_note_stale_is_accessible(cli_runner, tmp_vault):
    """pkm note stale is accessible as a subcommand of note."""
    result = cli_runner("note", "stale", "--days", "9999")
    assert result.exit_code == 0


def test_note_orphans_is_accessible(cli_runner, tmp_vault):
    """pkm note orphans is accessible as a subcommand of note."""
    result = cli_runner("note", "orphans")
    assert result.exit_code == 0
