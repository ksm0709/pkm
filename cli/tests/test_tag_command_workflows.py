"""Scenario tests for tag command helper behavior and table workflows."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.commands import tag_commands
from pkm.config import VaultConfig


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


def _write_note(vault: VaultConfig, name: str, *, title: str, tags: list[str]) -> None:
    tag_lines = "\n".join(f"  - {tag}" for tag in tags)
    (vault.notes_dir / f"{name}.md").write_text(
        f"---\nid: {name}\ntitle: {title}\ntags:\n{tag_lines}\n---\n\nBody\n",
        encoding="utf-8",
    )


def test_ensure_tag_note_validates_creates_and_preserves_existing(tmp_vault) -> None:
    """ensure_tag_note rejects invalid names, creates valid notes, and preserves existing files."""
    with pytest.raises(click.BadParameter, match="Invalid tag name"):
        tag_commands.ensure_tag_note(tmp_vault, "../escape")

    created = tag_commands.ensure_tag_note(tmp_vault, "topic.one")
    assert created == tmp_vault.tags_dir / "topic.one.md"
    assert created.exists()
    assert "id: topic.one" in created.read_text(encoding="utf-8")

    created.write_text("custom tag body\n", encoding="utf-8")
    returned = tag_commands.ensure_tag_note(tmp_vault, "topic.one")
    assert returned == created
    assert created.read_text(encoding="utf-8") == "custom tag body\n"


def test_tag_helpers_skip_malformed_notes_and_preserve_cplusplus_tag(
    tmp_vault,
) -> None:
    """Tag helpers skip parse failures and keep c++ exact matching distinct from AND."""
    _write_note(tmp_vault, "cpp-note", title="C Plus Plus", tags=["c++", "systems"])
    _write_note(tmp_vault, "python-note", title="Python", tags=["python", "systems"])
    (tmp_vault.daily_dir / "2026-05-01.md").write_text(
        "---\nid: 2026-05-01\ntags:\n  - c++\n---\nDaily\n",
        encoding="utf-8",
    )
    (tmp_vault.notes_dir / "bad-yaml.md").write_text(
        "---\n: bad: yaml\n---\n", encoding="utf-8"
    )

    collected = tag_commands._collect_notes_with_tag(tmp_vault, "c++")
    assert {str(note.id) for note in collected} == {"cpp-note", "2026-05-01"}

    counts = dict(tag_commands.count_all_tags(tmp_vault))
    assert counts["c++"] == 2
    assert "bad-yaml" not in counts

    exact_mode, exact = tag_commands.search_by_tag_pattern(tmp_vault, "c++")
    assert exact_mode == "exact(c++)"
    assert {str(note.id) for note in exact} == {"cpp-note", "2026-05-01"}

    and_mode, and_matches = tag_commands.search_by_tag_pattern(
        tmp_vault, "python+systems"
    )
    assert and_mode == "AND(python, systems)"
    assert [note.id for note in and_matches] == ["python-note"]

    or_mode, or_matches = tag_commands.search_by_tag_pattern(tmp_vault, "python,c++")
    assert or_mode == "OR(python, c++)"
    assert {str(note.id) for note in or_matches} == {
        "cpp-note",
        "python-note",
        "2026-05-01",
    }

    glob_mode, glob_matches = tag_commands.search_by_tag_pattern(tmp_vault, "sys*")
    assert glob_mode == "glob(sys*)"
    assert {note.id for note in glob_matches} == {"cpp-note", "python-note"}


def test_tags_root_table_mode_lists_tag_counts(cli_runner) -> None:
    """The root tags table path renders known tag counts for human users."""
    result = cli_runner("tags", "--format", "table")

    assert result.exit_code == 0
    assert "database" in result.output
    assert "daily-notes" in result.output


def test_tags_show_table_displays_body_notes_and_empty_state(cli_runner, tmp_vault):
    """Tag show table mode displays tag body, tagged notes, and no-note state."""
    tag_file = tmp_vault.tags_dir / "ops.md"
    tag_file.write_text(
        "---\nid: ops\ndescription: Ops topic\ntags: []\n---\n\nOperational context.\n",
        encoding="utf-8",
    )
    _write_note(tmp_vault, "ops-note", title="Ops Note", tags=["ops"])

    result = cli_runner("tags", "show", "ops", "--format", "table")

    assert result.exit_code == 0
    assert "Ops topic" in result.output
    assert "Operational context." in result.output
    assert "Ops Note" in result.output

    empty = cli_runner("tags", "show", "empty-topic", "--format", "table")
    assert empty.exit_code == 0
    assert "No notes found with tag 'empty-topic'" in empty.output


def test_tags_show_json_includes_tag_note_body_and_note_count(cli_runner, tmp_vault):
    """Tag show JSON mode returns description/body and matching note metadata."""
    tag_file = tmp_vault.tags_dir / "json-topic.md"
    tag_file.write_text(
        "---\nid: json-topic\ndescription: JSON topic\ntags: []\n---\n\nJSON body.\n",
        encoding="utf-8",
    )
    _write_note(tmp_vault, "json-note", title="JSON Note", tags=["json-topic"])

    result = cli_runner("tags", "show", "json-topic")

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["tag"] == "json-topic"
    assert payload["description"] == "JSON topic"
    assert payload["body"] == "JSON body."
    assert payload["count"] == 1
    assert payload["notes"][0]["title"] == "JSON Note"


def test_tags_search_table_modes_show_matches_and_empty_state(cli_runner, tmp_vault):
    """Tag search table mode handles matched and unmatched patterns."""
    _write_note(tmp_vault, "table-match", title="Table Match", tags=["table-tag"])

    matched = cli_runner("tags", "search", "table-tag", "--format", "table")
    assert matched.exit_code == 0
    assert "Table Match" in matched.output
    assert "1 note(s) found" in matched.output

    empty = cli_runner("tags", "search", "absent-tag", "--format", "table")
    assert empty.exit_code == 0
    assert "No notes found matching exact(absent-tag)" in empty.output


def test_tags_edit_runs_editor_and_reports_nonzero_return(
    cli_runner, tmp_vault, monkeypatch
) -> None:
    """Tag edit creates the tag note, launches the configured editor, and warns on failure."""
    calls = []
    monkeypatch.setattr(
        "pkm.config.load_config", lambda: {"defaults": {"editor": "code --wait"}}
    )
    monkeypatch.setattr(
        "pkm.editor.get_editor", lambda config: config["defaults"]["editor"]
    )

    def fake_run(args):
        calls.append(args)
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = cli_runner("tags", "edit", "edit-topic")

    assert result.exit_code == 0
    assert "Editor exited with code 7" in result.output
    assert (tmp_vault.tags_dir / "edit-topic.md").exists()
    assert calls == [["code", "--wait", str(tmp_vault.tags_dir / "edit-topic.md")]]
