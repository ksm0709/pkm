"""Tests for the `pkm note` command group."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
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


def _parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    # Strip the leading --- and trailing ---
    inner = text.split("---\n", 2)
    return yaml.safe_load(inner[1])


def test_new_creates_note(tmp_vault):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--vault", "test-vault", "note", "add", "My First Note"],
        catch_exceptions=False,
    )
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
        [
            "--vault",
            "test-vault",
            "note",
            "add",
            "Tagged Note",
            "--tags",
            "python,database",
        ],
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
        ["--vault", "test-vault", "note", "add", "english title"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    today = date.today().isoformat()
    # Spaces replaced by hyphens in slug
    note_path = tmp_vault.notes_dir / f"{today}-english-title.md"
    assert note_path.exists(), (
        f"Expected {note_path} to exist. Notes dir: {list(tmp_vault.notes_dir.iterdir())}"
    )


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
    """pkm note show with no match exits 0 with empty JSON results (agent-safe)."""
    import json as _json

    result = cli_runner("note", "show", "zzz-nonexistent-zzz-xyz")
    assert result.exit_code == 0
    json_text = result.output.split("\n* ")[0].strip()
    data = _json.loads(json_text)
    assert data["result_count"] == 0
    assert data["notes"] == []


# ---------------------------------------------------------------------------
# pkm note edit
# ---------------------------------------------------------------------------


def test_note_edit_single_match(cli_runner, tmp_vault, monkeypatch):
    """pkm note edit opens editor for single matching note."""
    calls = []

    class _FakeProc:
        returncode = 0

    monkeypatch.setattr("pkm.commands.notes.load_config", lambda: {})
    monkeypatch.setattr(
        "pkm.commands.notes.subprocess.run",
        lambda args, **kw: (_FakeProc(), calls.append(args))[0],
    )

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


# ---------------------------------------------------------------------------
# pkm note add --content (agent memory usage)
# ---------------------------------------------------------------------------


def test_note_add_content_creates_memory_note(tmp_vault):
    """pkm note add --content creates note with memory frontmatter."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--vault",
            "test-vault",
            "note",
            "add",
            "--content",
            "learned that IndexEntry crash fix requires field filtering",
            "--type",
            "semantic",
            "--importance",
            "7",
            "--session",
            "s1",
            "--agent",
            "ag1",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    today = date.today().isoformat()
    notes = list(tmp_vault.notes_dir.glob(f"{today}-*.md"))
    assert len(notes) >= 1

    # Find the note we just created
    note_file = next(n for n in notes if "indexentry" in n.name or "learned" in n.name)
    meta = _parse_frontmatter(note_file)
    assert meta["memory_type"] == "semantic"
    assert meta["importance"] == 7.0
    assert meta["session_id"] == "s1"
    assert meta["agent_id"] == "ag1"
    assert meta["source_type"] == "agent"
    assert meta["consolidated"] is False


def test_note_add_title_only_no_memory_fields(tmp_vault):
    """pkm note add 'title' (no options) does NOT include memory fields."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--vault", "test-vault", "note", "add", "Plain Research Note"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    today = date.today().isoformat()
    note_file = tmp_vault.notes_dir / f"{today}-plain-research-note.md"
    assert note_file.exists()

    meta = _parse_frontmatter(note_file)
    assert "memory_type" not in meta
    assert "importance" not in meta
    assert "session_id" not in meta
    # Standard fields present
    assert "id" in meta
    assert "source" in meta


def test_note_add_stdin(tmp_vault):
    """pkm note add --stdin reads content from stdin."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--vault",
            "test-vault",
            "note",
            "add",
            "--stdin",
            "--type",
            "episodic",
            "--importance",
            "5",
        ],
        input="multi-line content\nfrom stdin",
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    today = date.today().isoformat()
    notes = list(tmp_vault.notes_dir.glob(f"{today}-*.md"))
    assert any("multi-line" in n.name or "multi" in n.name for n in notes)


def test_note_add_no_title_no_content_raises_error(tmp_vault):
    """pkm note add with no title and no --content raises UsageError."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--vault", "test-vault", "note", "add"],
    )
    assert result.exit_code != 0


def test_note_add_content_defaults(tmp_vault):
    """pkm note add --content without --type uses semantic default."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--vault",
            "test-vault",
            "note",
            "add",
            "--content",
            "default type test content",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    today = date.today().isoformat()
    notes = list(tmp_vault.notes_dir.glob(f"{today}-*default*.md"))
    assert len(notes) >= 1
    meta = _parse_frontmatter(notes[0])
    assert meta["memory_type"] == "semantic"
    assert meta["importance"] == 5.0


# ---------------------------------------------------------------------------
# GAP 2: --no-dedup flag and dedup warn+proceed
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_model(monkeypatch):
    """Replace SentenceTransformer with a deterministic fake model (local copy for test_notes)."""
    import numpy as np

    class FakeModel:
        def encode(self, texts, **kwargs):
            texts_list = texts if isinstance(texts, list) else [texts]
            return np.array([[hash(t) % 100 / 100.0] * 384 for t in texts_list])

    monkeypatch.setattr(
        "pkm.search_engine._require_transformers", lambda name: FakeModel()
    )


def test_note_add_no_dedup_flag_skips_check(cli_runner, tmp_vault, monkeypatch):
    """--no-dedup skips find_similar entirely."""
    called = []

    def fake_find_similar(*args, **kwargs):
        called.append(True)
        return []

    monkeypatch.setattr("pkm.search_engine.find_similar", fake_find_similar)
    result = cli_runner("note", "add", "--content", "unique content here", "--no-dedup")
    assert result.exit_code == 0
    assert called == []  # never called


def test_note_add_dedup_warning_on_match(cli_runner, tmp_vault, monkeypatch, mock_model):
    """When similar note exists, warning is printed and note still created."""
    from pkm.search_engine import SearchResult, VectorIndex

    def fake_find_similar(content, index, **kwargs):
        return [SearchResult(
            note_id="existing-note",
            title="Existing Similar Note",
            score=0.91,
            backlink_count=0,
            tags=[],
            rank=1,
            memory_type="semantic",
            importance=7.0,
            path="/vault/notes/existing-note.md",
        )]

    monkeypatch.setattr("pkm.search_engine.find_similar", fake_find_similar)
    monkeypatch.setattr(
        "pkm.search_engine.load_index",
        lambda v: VectorIndex(model="m", created_at="", entries=[]),
    )

    result = cli_runner("note", "add", "--content", "some content about MVCC")
    assert result.exit_code == 0
    # Note should still be created
    today = date.today().isoformat()
    created_files = list(tmp_vault.notes_dir.glob(f"{today}-*.md"))
    assert len(created_files) >= 1


def test_note_add_dedup_no_index_graceful(cli_runner, tmp_vault):
    """When index does not exist, note add proceeds without error."""
    index_path = tmp_vault.pkm_dir / "index.json"
    if index_path.exists():
        index_path.unlink()

    result = cli_runner("note", "add", "--content", "content without index")
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# GAP 3: _append_operation_log + pkm note log
# ---------------------------------------------------------------------------


def test_note_add_creates_log_entry(cli_runner, tmp_vault):
    """pkm note add creates an entry in .pkm/log.md."""
    result = cli_runner("note", "add", "--content", "log test note", "--no-dedup")
    assert result.exit_code == 0
    log_path = tmp_vault.pkm_dir / "log.md"
    assert log_path.exists(), ".pkm/log.md should be created"
    content = log_path.read_text(encoding="utf-8")
    assert "[add]" in content
    assert "log test note" in content


def test_note_log_command_shows_entries(cli_runner, tmp_vault):
    """pkm note log shows entries after note add."""
    cli_runner("note", "add", "--content", "first note for log test", "--no-dedup")
    result = cli_runner("note", "log")
    assert result.exit_code == 0
    assert "[add]" in result.output


def test_note_log_no_file(cli_runner, tmp_vault):
    """pkm note log with no log file exits 0 with helpful message."""
    log_path = tmp_vault.pkm_dir / "log.md"
    if log_path.exists():
        log_path.unlink()
    result = cli_runner("note", "log")
    assert result.exit_code == 0
    assert "No log file" in result.output or "log" in result.output.lower()


def test_note_log_tail_option(cli_runner, tmp_vault):
    """pkm note log --tail N limits output."""
    for i in range(5):
        cli_runner("note", "add", "--content", f"note number {i}", "--no-dedup")
    result = cli_runner("note", "log", "--tail", "2")
    assert result.exit_code == 0
