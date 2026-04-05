"""Tests for the `pkm new` note creation command."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig


def invoke_new(tmp_vault: VaultConfig, *args: str, monkeypatch=None):
    """Helper: invoke `pkm new` with the given args against tmp_vault."""
    runner = CliRunner()
    if monkeypatch is not None:
        monkeypatch.setattr("pkm.config.discover_vaults", lambda *a, **kw: {"test-vault": tmp_vault})
    return runner.invoke(main, ["--vault", "test-vault", "new", *args], catch_exceptions=False)


@pytest.fixture(autouse=True)
def patch_vaults(monkeypatch, tmp_vault):
    monkeypatch.setattr("pkm.config.discover_vaults", lambda *a, **kw: {"test-vault": tmp_vault})


def _parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    # Strip the leading --- and trailing ---
    inner = text.split("---\n", 2)
    return yaml.safe_load(inner[1])


def test_new_creates_note(tmp_vault):
    runner = CliRunner()
    result = runner.invoke(main, ["--vault", "test-vault", "new", "My First Note"], catch_exceptions=False)
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
        ["--vault", "test-vault", "new", "Tagged Note", "--tags", "python,database"],
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
        ["--vault", "test-vault", "new", "한글 제목"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    today = date.today().isoformat()
    # Korean slug fallback: spaces replaced by hyphens
    note_path = tmp_vault.notes_dir / f"{today}-한글-제목.md"
    assert note_path.exists(), f"Expected {note_path} to exist. Notes dir: {list(tmp_vault.notes_dir.iterdir())}"


def test_new_refuses_overwrite(tmp_vault):
    runner = CliRunner()
    args = ["--vault", "test-vault", "new", "Duplicate Note"]
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
        ["--vault", "test-vault", "new", "Source Test"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    today = date.today().isoformat()
    note_path = tmp_vault.notes_dir / f"{today}-source-test.md"
    assert note_path.exists()

    meta = _parse_frontmatter(note_path)
    assert meta["source"] == today
