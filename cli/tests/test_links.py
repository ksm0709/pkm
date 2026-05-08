"""CLI integration tests for link commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.commands.links import _extract_tags
from pkm.config import VaultConfig


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cli_runner(runner, tmp_vault: VaultConfig, monkeypatch):
    """Return a runner that invokes main with tmp_vault injected."""

    def invoke(*args):
        monkeypatch.setattr(
            "pkm.config.discover_vaults",
            lambda root=None: {"test-vault": tmp_vault},
        )
        monkeypatch.setattr("pkm.config.load_config", lambda: {})
        return runner.invoke(main, list(args), catch_exceptions=False)

    return invoke


def test_orphans_command_json_includes_count_and_tags(cli_runner):
    """JSON output exposes orphan filenames plus parsed tag metadata."""
    result = cli_runner("note", "orphans", "--format", "json")

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["count"] == len(payload["orphans"])

    by_filename = {item["filename"]: item for item in payload["orphans"]}
    assert by_filename["isolated-note.md"]["tags"] == ["untagged"]
    assert by_filename["untagged-note.md"]["tags"] == []


def test_orphans_command_table_lists_tags_and_summary(cli_runner):
    """Table output renders orphan filenames, tags, and an operator-facing count."""
    result = cli_runner("note", "orphans", "--format", "table")

    assert result.exit_code == 0
    assert "isolated-note.md" in result.output
    assert "untagged-note.md" in result.output
    assert "untagged" in result.output
    assert "orphan note(s) found" in result.output


def test_orphans_command_table_reports_clean_vault(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A vault with no orphan notes reports a clean table state."""
    vault_path = tmp_path / "clean-vault"
    notes_dir = vault_path / "notes"
    notes_dir.mkdir(parents=True)
    (vault_path / "daily").mkdir()
    (notes_dir / "a.md").write_text(
        "---\nid: a\ntags: []\n---\n\nRelated: [[b]]\n",
        encoding="utf-8",
    )
    (notes_dir / "b.md").write_text(
        "---\nid: b\ntags: []\n---\n\nRelated: [[a]]\n",
        encoding="utf-8",
    )
    vault = VaultConfig(name="clean-vault", path=vault_path)
    monkeypatch.setattr(
        "pkm.config.discover_vaults", lambda root=None: {"clean-vault": vault}
    )
    monkeypatch.setattr("pkm.config.load_config", lambda: {})

    result = runner.invoke(
        main,
        ["note", "orphans", "--format", "table"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "No orphan notes found" in result.output


def test_extract_tags_handles_inline_missing_and_unreadable_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Orphan metadata parsing handles inline tags and falls back safely."""
    inline = tmp_path / "inline.md"
    inline.write_text("---\nid: inline\ntags: [alpha, beta]\n---\n", encoding="utf-8")
    plain = tmp_path / "plain.md"
    plain.write_text("No frontmatter here", encoding="utf-8")

    assert _extract_tags(inline) == ["alpha", "beta"]
    assert _extract_tags(plain) == []

    def unreadable(self, *args, **kwargs):
        if self == inline:
            raise OSError("permission denied")
        return original_read_text(self, *args, **kwargs)

    original_read_text = Path.read_text
    monkeypatch.setattr(Path, "read_text", unreadable)
    assert _extract_tags(inline) == []
