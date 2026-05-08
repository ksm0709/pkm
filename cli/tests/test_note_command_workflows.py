"""Scenario tests for higher-level `pkm note` workflows."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from pkm.cli import main
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
