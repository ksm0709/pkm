"""Scenario tests for higher-level `pkm note` workflows."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import click
import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig
from pkm.search_engine import VectorIndex


@pytest.fixture(autouse=True)
def patch_vaults(monkeypatch, tmp_vault):
    monkeypatch.setattr(
        "pkm.config.discover_vaults", lambda *a, **kw: {"test-vault": tmp_vault}
    )


@pytest.fixture
def cli_runner(monkeypatch, tmp_vault):
    runner = CliRunner()

    def invoke(*args, catch_exceptions=False):
        monkeypatch.setattr(
            "pkm.config.discover_vaults",
            lambda *a, **kw: {"test-vault": tmp_vault},
        )
        return runner.invoke(
            main,
            ["--vault", "test-vault", *args],
            catch_exceptions=catch_exceptions,
        )

    return invoke


def test_note_search_json_suppresses_model_noise_and_passes_stale_warning(
    cli_runner, monkeypatch
) -> None:
    """JSON note search redirects noisy index/search output and forwards options."""
    calls = []
    search_result = SimpleNamespace(note_id="n1", title="Note", score=0.9)

    def fake_load_index(vault):
        print("stdout noise from model")
        return VectorIndex(model="m", created_at="", entries=[])

    def fake_search(query, vector_index, **kwargs):
        print("stderr-like noise")
        return [search_result]

    def fake_format(**kwargs):
        calls.append(kwargs)
        kwargs["console"].print(json.dumps({"ok": True}))

    monkeypatch.delenv("TOKENIZERS_PARALLELISM", raising=False)
    monkeypatch.setattr("pkm.search_engine.is_index_stale", lambda vault: True)
    monkeypatch.setattr("pkm.search_engine.load_index", fake_load_index)
    monkeypatch.setattr("pkm.search_engine.search", fake_search)
    monkeypatch.setattr("pkm.commands.search.format_search_results", fake_format)

    result = cli_runner(
        "note",
        "search",
        "query",
        "--top",
        "3",
        "--type",
        "semantic",
        "--min-importance",
        "4.5",
    )

    assert result.exit_code == 0
    assert "stdout noise from model" not in result.output
    assert "stderr-like noise" not in result.output
    assert json.loads(result.output) == {"ok": True}
    assert calls[0]["query"] == "query"
    assert calls[0]["results"] == [search_result]
    assert calls[0]["output_format"] == "json"
    assert (
        calls[0]["stale_warning"]
        == "Index may be out of date. Run 'pkm index' to rebuild."
    )
    assert calls[0]["vault"].name == "test-vault"
    assert calls[0]["console"] is not None
    assert calls[0]["results"][0].title == "Note"


def test_note_search_table_warns_on_stale_and_skips_format_when_empty(
    cli_runner, monkeypatch
) -> None:
    """Table note search owns stale/no-results messaging for human output."""
    format_results = MagicMock()
    monkeypatch.setattr("pkm.search_engine.is_index_stale", lambda vault: True)
    monkeypatch.setattr(
        "pkm.search_engine.load_index",
        lambda vault: VectorIndex(model="m", created_at="", entries=[]),
    )
    monkeypatch.setattr("pkm.search_engine.search", lambda *args, **kwargs: [])
    monkeypatch.setattr("pkm.commands.search.format_search_results", format_results)

    result = cli_runner("note", "search", "missing", "--format", "table")

    assert result.exit_code == 0
    assert "Warning:" in result.output
    assert "No results found." in result.output
    format_results.assert_not_called()


def test_note_search_table_formats_results_after_printing_stale_warning(
    cli_runner, monkeypatch
) -> None:
    """Table note search clears stale_warning before delegating formatted results."""
    calls = []
    search_result = SimpleNamespace(note_id="n1", title="Note", score=0.9)
    monkeypatch.setattr("pkm.search_engine.is_index_stale", lambda vault: True)
    monkeypatch.setattr(
        "pkm.search_engine.load_index",
        lambda vault: VectorIndex(model="m", created_at="", entries=[]),
    )
    monkeypatch.setattr(
        "pkm.search_engine.search", lambda *args, **kwargs: [search_result]
    )
    monkeypatch.setattr(
        "pkm.commands.search.format_search_results",
        lambda **kwargs: calls.append(kwargs),
    )

    result = cli_runner("note", "search", "note", "--format", "table")

    assert result.exit_code == 0
    assert "Warning:" in result.output
    assert calls[0]["output_format"] == "table"
    assert calls[0]["stale_warning"] is None
    assert calls[0]["results"] == [search_result]


def test_note_links_json_no_match_returns_error_payload(cli_runner) -> None:
    """JSON links no-match stays machine-readable while exiting nonzero."""
    result = cli_runner("note", "links", "not-present", catch_exceptions=True)

    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload == {"error": "No notes found matching 'not-present'"}


def test_note_links_table_no_match_exits_nonzero(cli_runner) -> None:
    """Table links no-match exits nonzero with a human message."""
    result = cli_runner(
        "note",
        "links",
        "not-present",
        "--format",
        "table",
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "No notes found" in result.output


def test_note_links_json_skips_unparsable_backlinks(cli_runner, tmp_vault, monkeypatch):
    """JSON links keeps valid backlinks and skips parse failures."""
    valid = tmp_vault.notes_dir / "valid-backlink.md"
    invalid = tmp_vault.notes_dir / "invalid-backlink.md"
    valid.write_text(
        "---\nid: valid-backlink\ntitle: Valid Backlink\n---\nBody\n", encoding="utf-8"
    )
    invalid.write_text("---\n: bad: yaml\n---\n", encoding="utf-8")

    from pkm.frontmatter import parse as real_parse

    def fake_parse(path):
        if Path(path) == invalid:
            raise RuntimeError("bad frontmatter")
        return real_parse(path)

    monkeypatch.setattr(
        "pkm.commands.notes.find_backlinks", lambda vault, note_id: [valid, invalid]
    )
    monkeypatch.setattr("pkm.commands.notes.parse", fake_parse)

    result = cli_runner("note", "links", "mvcc")

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["note"] == "2026-04-01-mvcc"
    assert payload["count"] == 1
    assert payload["backlinks"] == [
        {"title": "Valid Backlink", "description": "", "path": "valid-backlink.md"}
    ]


def test_note_links_table_no_backlinks_message(cli_runner, monkeypatch) -> None:
    """Table links reports the no-backlinks state without error."""
    monkeypatch.setattr("pkm.commands.notes.find_backlinks", lambda vault, note_id: [])

    result = cli_runner("note", "links", "mvcc", "--format", "table")

    assert result.exit_code == 0
    assert "No backlinks found" in result.output


def test_note_group_without_subcommand_prints_help(cli_runner) -> None:
    """Bare `pkm note` gives the user command help instead of doing nothing."""
    result = cli_runner("note")

    assert result.exit_code == 0
    assert "Manage notes" in result.output
    assert "add" in result.output
    assert "show" in result.output


def test_note_add_vault_option_writes_to_named_vault(
    monkeypatch, tmp_path, tmp_vault
) -> None:
    """`note add --vault` overrides the active vault for the created note."""
    other_path = tmp_path / "other-vault"
    for name in ("daily", "notes", ".pkm"):
        (other_path / name).mkdir(parents=True)
    other_vault = VaultConfig(name="other-vault", path=other_path)
    vaults = {"test-vault": tmp_vault, "other-vault": other_vault}
    monkeypatch.setattr("pkm.config.discover_vaults", lambda *a, **kw: vaults)

    result = CliRunner().invoke(
        main,
        [
            "--vault",
            "test-vault",
            "note",
            "add",
            "Routed Note",
            "--vault",
            "other-vault",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    today = date.today().isoformat()
    assert (other_vault.notes_dir / f"{today}-routed-note.md").exists()
    assert not (tmp_vault.notes_dir / f"{today}-routed-note.md").exists()


def test_note_rename_surfaces_lifecycle_errors(cli_runner, monkeypatch) -> None:
    """Rename command maps lifecycle validation failures to CLI errors."""
    monkeypatch.setattr(
        "pkm.commands.notes.rename_note_id",
        lambda *args: (_ for _ in ()).throw(ValueError("invalid note id")),
    )

    result = cli_runner("note", "rename", "old", "bad/id", catch_exceptions=True)

    assert result.exit_code != 0
    assert "invalid note id" in result.output


def test_note_show_markdown_no_match_exits_with_human_message(
    cli_runner,
) -> None:
    """Markdown show no-match is a human-facing failure, unlike JSON no-match."""
    result = cli_runner(
        "note",
        "show",
        "not-present",
        "--format",
        "md",
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "No notes found" in result.output


def test_note_show_markdown_prints_selected_note(cli_runner) -> None:
    """Markdown show returns the first matching note body for human reading."""
    result = cli_runner("note", "show", "mvcc", "--format", "md")

    assert result.exit_code == 0
    assert "MVCC is a concurrency control technique." in result.output
    assert "id: 2026-04-01-mvcc" in result.output


def test_note_show_json_skips_bad_backlinks_and_includes_graph_context(
    cli_runner, tmp_vault, monkeypatch
) -> None:
    """JSON show keeps usable backlink context and tolerates broken backlink files."""
    valid = tmp_vault.notes_dir / "valid-show-backlink.md"
    broken = tmp_vault.notes_dir / "broken-show-backlink.md"
    valid.write_text(
        "---\nid: valid-show-backlink\ntitle: Valid Show Backlink\n---\nBody\n",
        encoding="utf-8",
    )
    broken.write_text("---\n: bad: yaml\n---\n", encoding="utf-8")

    from pkm.frontmatter import parse as real_parse

    def fake_parse(path):
        if Path(path) == broken:
            raise RuntimeError("bad frontmatter")
        return real_parse(path)

    monkeypatch.setattr(
        "pkm.commands.notes.find_backlinks", lambda vault, note_id: [valid, broken]
    )
    monkeypatch.setattr("pkm.commands.notes.parse", fake_parse)
    monkeypatch.setattr(
        "pkm.search_engine.get_graph_context_via_daemon",
        lambda note_id, vault, depth: {"note_id": note_id, "depth": depth},
        raising=False,
    )

    result = cli_runner("note", "show", "mvcc", "--top", "1", "--depth", "2")

    assert result.exit_code == 0
    payload = json.loads(result.output)
    note = payload["notes"][0]
    assert note["backlinks"] == ["Valid Show Backlink"]
    assert note["graph_context"] == {"note_id": "2026-04-01-mvcc", "depth": 2}


def test_note_links_table_renders_valid_backlinks_and_skips_broken_files(
    cli_runner, tmp_vault, monkeypatch
) -> None:
    """Table links presents valid backlinks without failing on corrupt notes."""
    valid = tmp_vault.notes_dir / "valid-table-backlink.md"
    broken = tmp_vault.notes_dir / "broken-table-backlink.md"
    valid.write_text(
        "---\n"
        "id: valid-table-backlink\n"
        "title: Valid Table Backlink\n"
        "description: Human readable context\n"
        "---\nBody\n",
        encoding="utf-8",
    )
    broken.write_text("---\n: bad: yaml\n---\n", encoding="utf-8")

    from pkm.frontmatter import parse as real_parse

    def fake_parse(path):
        if Path(path) == broken:
            raise RuntimeError("bad frontmatter")
        return real_parse(path)

    monkeypatch.setattr(
        "pkm.commands.notes.find_backlinks", lambda vault, note_id: [valid, broken]
    )
    monkeypatch.setattr("pkm.commands.notes.parse", fake_parse)

    result = cli_runner("note", "links", "mvcc", "--format", "table")

    assert result.exit_code == 0
    assert "Valid Table Backlink" in result.output
    assert "Human readable context" in result.output
    assert "broken-table-backlink" not in result.output


def test_note_edit_nonzero_editor_return_warns_but_exits_zero(
    cli_runner, monkeypatch
) -> None:
    """Editor failures are reported as warnings without failing the command."""
    monkeypatch.setattr("pkm.commands.notes.load_config", lambda: {})
    monkeypatch.setattr(
        "pkm.commands.notes.subprocess.run",
        lambda args: SimpleNamespace(returncode=7),
    )

    result = cli_runner("note", "edit", "mvcc")

    assert result.exit_code == 0
    assert "Editor exited with code 7" in result.output


def test_note_auto_link_requires_target_even_with_dry_run(cli_runner) -> None:
    """auto-link validates that either note_id or --all selects work."""
    result = cli_runner("note", "auto-link", "--dry-run", catch_exceptions=True)

    assert result.exit_code != 0
    assert "Must provide either note_id or --all" in result.output


def test_note_auto_link_missing_ast_cache_exits_nonzero(cli_runner) -> None:
    """auto-link refuses to run when the AST cache is absent."""
    result = cli_runner(
        "note", "auto-link", "--all", "--dry-run", catch_exceptions=True
    )

    assert result.exit_code != 0
    assert "AST cache not found" in result.output


def test_note_auto_link_dry_run_detects_plain_title_without_writing(
    cli_runner, tmp_vault, monkeypatch
) -> None:
    """auto-link dry-run reports files that would receive title wikilinks."""
    target = tmp_vault.notes_dir / "plain-reference.md"
    target.write_text(
        "---\nid: plain-reference\ntitle: Plain Reference\ntags: []\n---\n\n"
        "Mention Database Isolation plainly.\n",
        encoding="utf-8",
    )
    title_note = tmp_vault.notes_dir / "database-isolation.md"
    title_note.write_text(
        "---\nid: database-isolation\ntitle: Database Isolation\ntags: []\n---\n\nBody\n",
        encoding="utf-8",
    )
    (tmp_vault.pkm_dir / "ast.db").write_text("", encoding="utf-8")

    class FakeCache:
        def __init__(self, db_path):
            self.db_path = db_path

        def get(self, note_id):
            if note_id != "plain-reference":
                return None
            return SimpleNamespace(
                path=str(target),
                plain_text_offsets=[
                    {
                        "text": "Mention Database Isolation plainly.",
                        "offset": 0,
                        "length": len("Mention Database Isolation plainly."),
                    }
                ],
            )

    monkeypatch.setattr("pkm.graph.ASTCache", FakeCache)

    original = target.read_text(encoding="utf-8")
    result = cli_runner("note", "auto-link", "plain-reference", "--dry-run")

    assert result.exit_code == 0
    assert "Would update links in plain-reference" in result.output
    assert target.read_text(encoding="utf-8") == original


def test_note_auto_link_callback_writes_links_and_skips_ineligible_offsets(
    tmp_vault, monkeypatch
) -> None:
    """Auto-link mutation links other note titles while skipping self/blank/missing data."""
    target = tmp_vault.notes_dir / "plain-reference.md"
    body = "Plain Reference mentions Database Isolation.\n"
    target.write_text(
        "---\nid: plain-reference\ntitle: Plain Reference\ntags: []\n---\n\n" + body,
        encoding="utf-8",
    )
    title_note = tmp_vault.notes_dir / "database-isolation-title.md"
    title_note.write_text(
        "---\n"
        "id: database-isolation-title\n"
        "title: Database Isolation\n"
        "tags: []\n"
        "---\n\nBody\n",
        encoding="utf-8",
    )
    missing_metadata_note = tmp_vault.notes_dir / "missing-metadata.md"
    missing_metadata_note.write_text(
        "---\nid: missing-metadata\ntitle: Missing Metadata\ntags: []\n---\n\nBody\n",
        encoding="utf-8",
    )
    (tmp_vault.pkm_dir / "ast.db").write_text("", encoding="utf-8")

    class FakeCache:
        def __init__(self, db_path):
            self.db_path = db_path

        def get(self, note_id):
            if note_id == "plain-reference":
                return SimpleNamespace(
                    path=str(target),
                    plain_text_offsets=[
                        {"text": "   ", "offset": len(body), "length": 3},
                        {"text": body, "offset": 0, "length": len(body)},
                    ],
                )
            return None

    monkeypatch.setattr("pkm.graph.ASTCache", FakeCache)

    from pkm.commands.notes import auto_link

    with click.Context(auto_link, obj={"vault": tmp_vault}):
        auto_link.callback(note_id=None, all_notes=True, dry_run=False)

    updated = target.read_text(encoding="utf-8")
    assert "Plain Reference mentions [[Database Isolation]]." in updated
    assert "[[Plain Reference]]" not in updated
    assert "[[Missing Metadata]]" not in updated
    assert missing_metadata_note.read_text(encoding="utf-8").endswith("Body\n")


def test_note_split_requires_target_even_with_dry_run(cli_runner) -> None:
    """split validates that either note_id or --all selects work."""
    result = cli_runner("note", "split", "--dry-run", catch_exceptions=True)

    assert result.exit_code != 0
    assert "Must provide either note_id or --all" in result.output


def test_note_split_dry_run_uses_heading_fallback_without_writing(
    cli_runner, tmp_vault
) -> None:
    """split dry-run can plan a heading-based split without AST metadata."""
    note_path = tmp_vault.notes_dir / "split-source.md"
    note_path.write_text(
        "---\nid: split-source\ntitle: Split Source\ntags: []\n---\n\n"
        "Intro\n\n## First\nA\n\n## Second\nB\n",
        encoding="utf-8",
    )
    original = note_path.read_text(encoding="utf-8")

    result = cli_runner("note", "split", "split-source", "--dry-run")

    assert result.exit_code == 0
    assert "Would split split-source into 3 notes" in result.output
    assert note_path.read_text(encoding="utf-8") == original


def test_note_split_one_part_note_is_noop(cli_runner, tmp_vault) -> None:
    """split dry-run exits quietly when no split points exist."""
    note_path = tmp_vault.notes_dir / "one-part.md"
    note_path.write_text(
        "---\nid: one-part\ntitle: One Part\ntags: []\n---\n\nOnly one body.\n",
        encoding="utf-8",
    )

    result = cli_runner("note", "split", "one-part", "--dry-run")

    assert result.exit_code == 0
    assert result.output == ""
