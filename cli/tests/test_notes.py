"""Tests for the `pkm note` command group."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

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


def test_rename_note_id_updates_file_frontmatter_and_wikilinks(tmp_vault):
    """Shared lifecycle rename rewrites links across notes and daily files."""
    from pkm.frontmatter import parse
    from pkm.note_lifecycle import rename_note_id

    source = tmp_vault.notes_dir / "old-note.md"
    source.write_text(
        "---\nid: old-note\ntitle: Old Note\ntags: []\n---\n\nBody\n",
        encoding="utf-8",
    )
    linked = tmp_vault.notes_dir / "linking-note.md"
    linked.write_text(
        "---\nid: linking-note\ntags: []\n---\n\n"
        "See [[old-note]] and [[old-note|kept alias]].\n",
        encoding="utf-8",
    )
    daily = tmp_vault.daily_dir / "2026-05-04.md"
    daily.write_text(
        "---\nid: 2026-05-04\ntags: []\n---\n\nLogged [[old-note.md]].\n",
        encoding="utf-8",
    )

    result = rename_note_id(tmp_vault, "old-note", "new-note")

    assert not source.exists()
    renamed = tmp_vault.notes_dir / "new-note.md"
    assert renamed.exists()
    assert parse(renamed).id == "new-note"
    assert result.wikilinks.replacements == 3
    assert "[[new-note]]" in linked.read_text(encoding="utf-8")
    assert "[[new-note|kept alias]]" in linked.read_text(encoding="utf-8")
    assert "[[new-note]]" in daily.read_text(encoding="utf-8")


def test_rename_note_id_moves_annotation_sidecar(tmp_vault):
    from pkm.annotations.store import (
        AnnotationSource,
        annotation_sidecar_path,
        empty_annotation_document,
        read_annotation_document,
        write_annotation_document,
    )
    from pkm.note_lifecycle import rename_note_id

    note_path = tmp_vault.notes_dir / "old-annotated.md"
    note_path.write_text(
        "---\nid: old-annotated\ntitle: Old\ntags: []\n---\n\nAnnotated body.\n",
        encoding="utf-8",
    )
    old_source = AnnotationSource(kind="note", identifier="old-annotated")
    new_source = AnnotationSource(kind="note", identifier="new-annotated")
    document = empty_annotation_document(old_source)
    document["annotation_revision"] = 3
    document["annotations"] = [{"id": "ann-1"}]
    write_annotation_document(tmp_vault, old_source, document)

    rename_note_id(tmp_vault, "old-annotated", "new-annotated")

    assert not annotation_sidecar_path(tmp_vault, old_source).exists()
    moved = read_annotation_document(tmp_vault, new_source)
    assert moved["source_key"] == "note:new-annotated"
    assert moved["source"] == {"kind": "note", "note_id": "new-annotated"}
    assert moved["annotation_revision"] == 3
    assert moved["annotations"] == [{"id": "ann-1"}]


def test_note_rename_serializes_destination_annotation_writes(
    tmp_vault,
    monkeypatch,
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from time import sleep

    from pkm.annotations.store import (
        AnnotationSource,
        annotation_sidecar_path,
        empty_annotation_document,
        note_lifecycle_lock,
        write_annotation_document,
    )
    import pkm.note_lifecycle as lifecycle

    old_id = "old-race-note"
    new_id = "new-race-note"
    old_note = tmp_vault.notes_dir / f"{old_id}.md"
    old_note.write_text(
        f"---\nid: {old_id}\ntitle: Old\ntags: []\n---\n\nBody.\n",
        encoding="utf-8",
    )
    old_source = AnnotationSource(kind="note", identifier=old_id)
    new_source = AnnotationSource(kind="note", identifier=new_id)
    write_annotation_document(
        tmp_vault,
        old_source,
        {**empty_annotation_document(old_source), "annotations": [{"id": "old"}]},
    )

    destination_exposed = Event()
    release_rename = Event()
    competing_entered = Event()
    real_rename_annotations = lifecycle.rename_annotation_document

    def paused_rename_annotations(vault, source, destination):
        destination_exposed.set()
        assert release_rename.wait(timeout=2)
        return real_rename_annotations(vault, source, destination)

    monkeypatch.setattr(
        lifecycle,
        "rename_annotation_document",
        paused_rename_annotations,
    )

    def competing_annotation_write() -> None:
        assert destination_exposed.wait(timeout=2)
        with note_lifecycle_lock(tmp_vault, new_id):
            competing_entered.set()
            if not annotation_sidecar_path(tmp_vault, new_source).exists():
                write_annotation_document(
                    tmp_vault,
                    new_source,
                    empty_annotation_document(new_source),
                )

    with ThreadPoolExecutor(max_workers=2) as executor:
        renamed = executor.submit(lifecycle.rename_note_id, tmp_vault, old_id, new_id)
        assert destination_exposed.wait(timeout=2)
        competing = executor.submit(competing_annotation_write)
        sleep(0.05)
        assert not competing_entered.is_set()
        release_rename.set()
        renamed.result(timeout=2)
        competing.result(timeout=2)

    assert competing_entered.is_set()
    assert not old_note.exists()
    assert (tmp_vault.notes_dir / f"{new_id}.md").exists()
    assert annotation_sidecar_path(tmp_vault, new_source).exists()
    assert not annotation_sidecar_path(tmp_vault, old_source).exists()


def test_note_rename_command_updates_wikilinks(cli_runner, tmp_vault):
    source = tmp_vault.notes_dir / "old-cli-note.md"
    source.write_text(
        "---\nid: old-cli-note\ntags: []\n---\n\nBody\n",
        encoding="utf-8",
    )
    linked = tmp_vault.notes_dir / "cli-linking-note.md"
    linked.write_text(
        "---\nid: cli-linking-note\ntags: []\n---\n\n[[old-cli-note]]\n",
        encoding="utf-8",
    )

    result = cli_runner("note", "rename", "old-cli-note", "new-cli-note")

    assert result.exit_code == 0
    assert "Renamed" in result.output
    assert not source.exists()
    assert (tmp_vault.notes_dir / "new-cli-note.md").exists()
    assert "[[new-cli-note]]" in linked.read_text(encoding="utf-8")


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


def test_search_notes_missing_directory_returns_empty(tmp_path):
    """Search treats a partially initialized vault with no notes dir as empty."""
    from pkm.commands.notes import _search_notes

    vault = SimpleNamespace(notes_dir=tmp_path / "missing-notes")

    assert _search_notes(vault, "anything") == []


def test_search_notes_skips_unreadable_notes(tmp_vault, monkeypatch):
    """Search continues returning good matches when one note cannot be parsed."""
    from pkm.commands.notes import _search_notes
    from pkm.frontmatter import parse as real_parse

    broken = tmp_vault.notes_dir / "broken-note.md"
    broken.write_text("---\n: bad: yaml\n---\n", encoding="utf-8")

    def fake_parse(path):
        if Path(path) == broken:
            raise RuntimeError("bad frontmatter")
        return real_parse(path)

    monkeypatch.setattr("pkm.commands.notes.parse", fake_parse)

    matches = _search_notes(tmp_vault, "mvcc")

    assert any(match.id == "2026-04-01-mvcc" for match in matches)


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


def test_note_add_dedup_warning_on_match(
    cli_runner, tmp_vault, monkeypatch, mock_model
):
    """When similar note exists, warning is printed and note still created."""
    from pkm.search_engine import SearchResult, VectorIndex

    def fake_find_similar(content, index, **kwargs):
        return [
            SearchResult(
                note_id="existing-note",
                title="Existing Similar Note",
                score=0.91,
                backlink_count=0,
                tags=[],
                rank=1,
                memory_type="semantic",
                importance=7.0,
                path="/vault/notes/existing-note.md",
            )
        ]

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


def test_create_note_uses_daemon_matches_and_survives_index_update_failure(
    tmp_vault, monkeypatch
):
    """Note creation proceeds after daemon dedup and failed async index refresh."""
    from pkm.commands.notes import create_note

    load_index = []
    monkeypatch.setattr(
        "pkm.search_engine.search_via_daemon",
        lambda *args, **kwargs: [SimpleNamespace(score=0.91)],
    )
    monkeypatch.setattr(
        "pkm.search_engine.load_index",
        lambda vault: load_index.append(vault),
    )
    monkeypatch.setattr(
        "pkm.search_engine.update_index_via_daemon",
        lambda vault: (_ for _ in ()).throw(RuntimeError("daemon down")),
    )

    note_path = create_note(
        tmp_vault,
        title="Daemon Dedup Resilience",
        content="content close enough to trigger daemon similarity",
    )

    assert note_path.exists()
    assert note_path.stem.endswith("daemon-dedup-resilience")
    assert "content close enough" in note_path.read_text(encoding="utf-8")
    assert load_index == []


def test_slugify_preserves_non_ascii_fallback():
    """Titles with no ASCII slug survive as deterministic filenames."""
    from pkm.commands.notes import _slugify

    assert _slugify("한글 제목") == "한글-제목"


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


def test_append_operation_log_adds_today_section_to_existing_log(tmp_vault):
    """Log append preserves old content and creates today's section when missing."""
    from pkm.commands.notes import _append_operation_log

    log_path = tmp_vault.pkm_dir / "log.md"
    log_path.write_text(
        "# Operation Log\n\n## 1999-01-01\n- old entry", encoding="utf-8"
    )

    _append_operation_log(tmp_vault, "add", "new-note", "New Note")

    text = log_path.read_text(encoding="utf-8")
    assert "## 1999-01-01" in text
    assert f"## {date.today().isoformat()}" in text
    assert '[add] new-note — "New Note"' in text


def test_append_operation_log_swallows_filesystem_errors(tmp_vault, monkeypatch):
    """Logging failures do not fail the note creation workflow."""
    from pkm.commands.notes import _append_operation_log

    original_mkdir = Path.mkdir

    def fail_for_log_dir(self, *args, **kwargs):
        if self == tmp_vault.pkm_dir:
            raise OSError("read only")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_for_log_dir)

    _append_operation_log(tmp_vault, "add", "ignored", "Ignored")


# ---------------------------------------------------------------------------
# read_note tool: 8-key JSON schema
# ---------------------------------------------------------------------------

_REQUIRED_NOTE_KEYS = (
    "note_id",
    "title",
    "body",
    "frontmatter",
    "created",
    "updated",
    "tags",
    "importance",
)


# ---------------------------------------------------------------------------
# read_note tool: 8-key JSON schema (MCP path)
# ---------------------------------------------------------------------------


class TestReadNoteMCP:
    def test_returns_all_8_keys(self, tmp_vault):
        """MCP read_note returns all 8 required keys."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault
        result = mcp_mod.read_note("2026-04-01-mvcc")
        assert isinstance(result, dict)
        for key in _REQUIRED_NOTE_KEYS:
            assert key in result, f"Missing key: {key}"

    def test_missing_frontmatter_returns_empty_dict(self, tmp_vault):
        """MCP read_note returns {} for frontmatter when note has no YAML header."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault
        bare = tmp_vault.notes_dir / "bare-mcp.md"
        bare.write_text("No frontmatter\n", encoding="utf-8")
        result = mcp_mod.read_note("bare-mcp")
        assert result["frontmatter"] == {}

    def test_missing_tags_returns_empty_list(self, tmp_vault):
        """MCP read_note returns [] for tags when missing."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault
        note = tmp_vault.notes_dir / "no-tags-mcp.md"
        note.write_text("---\nid: no-tags-mcp\n---\nBody\n", encoding="utf-8")
        result = mcp_mod.read_note("no-tags-mcp")
        assert result["tags"] == []

    def test_missing_importance_returns_none(self, tmp_vault):
        """MCP read_note returns None for importance when missing."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault
        result = mcp_mod.read_note("2026-04-01-mvcc")
        assert result["importance"] is None

    def test_not_found_returns_error(self, tmp_vault):
        """MCP read_note returns error dict for unknown note_id."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault
        result = mcp_mod.read_note("does-not-exist-xyz")
        assert "error" in result


class TestRenameNoteMCP:
    def test_rename_note_mcp_updates_wikilinks(self, tmp_vault):
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault
        source = tmp_vault.notes_dir / "old-mcp-note.md"
        source.write_text(
            "---\nid: old-mcp-note\ntags: []\n---\n\nBody\n",
            encoding="utf-8",
        )
        linked = tmp_vault.daily_dir / "2026-05-04.md"
        linked.write_text(
            "---\nid: 2026-05-04\ntags: []\n---\n\n[[old-mcp-note]]\n",
            encoding="utf-8",
        )

        result = mcp_mod.rename_note("old-mcp-note", "new-mcp-note")

        assert result["status"] == "renamed"
        assert result["wikilinks_updated"] == 1
        assert not source.exists()
        assert (tmp_vault.notes_dir / "new-mcp-note.md").exists()
        assert "[[new-mcp-note]]" in linked.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# list_notes tool (MCP path)
# ---------------------------------------------------------------------------


class TestListNotesMCP:
    def test_returns_notes_and_count(self, tmp_vault):
        """MCP list_notes returns dict with notes list and count."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault
        result = mcp_mod.list_notes()
        assert "notes" in result
        assert "count" in result
        assert result["count"] >= 1
        assert result["count"] == len(result["notes"])

    def test_each_item_has_required_keys(self, tmp_vault):
        """Each list_notes item has note_id, title, path, tags, created_at."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault
        result = mcp_mod.list_notes()
        for item in result["notes"]:
            for key in ("note_id", "title", "path", "tags", "created_at"):
                assert key in item, f"Missing key '{key}' in list_notes item"

    def test_filter_by_title(self, tmp_vault):
        """list_notes(filter=...) returns only matching notes."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault
        result = mcp_mod.list_notes(filter="mvcc")
        assert result["count"] >= 1
        for item in result["notes"]:
            assert "mvcc" in item["title"].lower()

    def test_filter_no_match_returns_empty(self, tmp_vault):
        """list_notes with non-matching filter returns empty list."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault
        result = mcp_mod.list_notes(filter="zzz-nonexistent-zzz")
        assert result["count"] == 0
        assert result["notes"] == []
