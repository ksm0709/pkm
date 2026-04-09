"""Tests for JSON output and agent-friendly formatting of search/note commands."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def vault_env(tmp_vault: VaultConfig, monkeypatch):
    monkeypatch.setenv("PKM_VAULTS_ROOT", str(tmp_vault.path.parent))
    monkeypatch.setenv("PKM_DEFAULT_VAULT", tmp_vault.name)
    return tmp_vault


@pytest.fixture
def indexed_vault(vault_env, tmp_vault, runner):
    """Build search index for the tmp vault before tests."""
    runner.invoke(main, ["index"])
    return tmp_vault


# ---------------------------------------------------------------------------
# pkm search — JSON default
# ---------------------------------------------------------------------------


def test_search_defaults_to_json(runner, indexed_vault):
    """pkm search without --format must output valid JSON."""
    result = runner.invoke(main, ["search", "database"])
    assert result.exit_code == 0
    # Extract JSON portion (before action guide lines)
    json_part = result.output.split("\n\n*")[0].split("\n* ")[0].strip()
    data = json.loads(json_part)
    assert "query" in data
    assert "result_count" in data
    assert "results" in data


def test_search_table_requires_explicit_flag(runner, indexed_vault):
    """pkm search --format table outputs Rich Table (not JSON)."""
    result = runner.invoke(main, ["search", "database", "--format", "table"])
    assert result.exit_code == 0
    assert "{" not in result.output[:5]  # Not JSON


def test_search_json_fields(runner, indexed_vault):
    """JSON output must use 'score' field (not 'similarity')."""
    result = runner.invoke(main, ["search", "mvcc"])
    assert result.exit_code == 0
    json_text = result.output.split("\n* ")[0].strip()
    data = json.loads(json_text)
    if data["results"]:
        r = data["results"][0]
        assert "score" in r, "Must use 'score' not 'similarity'"
        assert "similarity" not in r
        assert "rank" in r
        assert "title" in r
        assert "importance" in r
        assert "note_id" in r


def test_search_json_action_guide_on_stdout(runner, indexed_vault):
    """Text action guide must appear on stdout after JSON."""
    result = runner.invoke(main, ["search", "database"])
    assert result.exit_code == 0
    assert "pkm note show" in result.output
    assert "pkm search" in result.output
    assert "pkm note add" in result.output


def test_search_json_description_from_frontmatter(runner, indexed_vault, tmp_vault):
    """description field populated from frontmatter when present."""
    note = tmp_vault.notes_dir / "desc-test.md"
    note.write_text(
        "---\nid: desc-test\ndescription: My frontmatter description\ntags: []\n---\nBody content.\n",
        encoding="utf-8",
    )
    runner.invoke(main, ["index"])
    result = runner.invoke(main, ["search", "frontmatter description"])
    assert result.exit_code == 0
    json_text = result.output.split("\n* ")[0].strip()
    data = json.loads(json_text)
    matching = [r for r in data["results"] if r["title"] == "desc-test"]
    if matching:
        assert matching[0]["description"] == "My frontmatter description"


def test_search_json_is_valid_parseable(runner, indexed_vault):
    """pkm search JSON output must be parseable by json.loads (no model noise)."""
    result = runner.invoke(main, ["search", "test"])
    assert result.exit_code == 0
    # The JSON blob is the first chunk before the action guide
    lines = result.output.split("\n")
    json_lines = []
    for line in lines:
        if line.startswith("* ") or (
            json_lines
            and line == ""
            and any(ln.startswith("* ") for ln in lines[lines.index(line) :])
        ):
            break
        json_lines.append(line)
    json_text = "\n".join(json_lines).strip()
    data = json.loads(json_text)  # Must not raise
    assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# pkm note search
# ---------------------------------------------------------------------------


def test_note_search_defaults_to_json(runner, indexed_vault):
    """pkm note search must output JSON by default."""
    result = runner.invoke(main, ["note", "search", "database"])
    assert result.exit_code == 0
    json_text = result.output.split("\n* ")[0].strip()
    data = json.loads(json_text)
    assert "results" in data


def test_note_search_results_match_pkm_search(runner, indexed_vault):
    """pkm note search and pkm search must return identical result counts."""
    r1 = runner.invoke(main, ["search", "mvcc", "--top", "3"])
    r2 = runner.invoke(main, ["note", "search", "mvcc", "--top", "3"])
    assert r1.exit_code == 0
    assert r2.exit_code == 0
    d1 = json.loads(r1.output.split("\n* ")[0].strip())
    d2 = json.loads(r2.output.split("\n* ")[0].strip())
    assert d1["result_count"] == d2["result_count"]


def test_note_search_action_guide(runner, indexed_vault):
    result = runner.invoke(main, ["note", "search", "database"])
    assert result.exit_code == 0
    assert "pkm note show" in result.output


# ---------------------------------------------------------------------------
# pkm note show — JSON redesign
# ---------------------------------------------------------------------------


def test_note_show_defaults_to_json(runner, vault_env):
    """pkm note show without --format outputs JSON array."""
    result = runner.invoke(main, ["note", "show", "mvcc"])
    assert result.exit_code == 0
    json_text = result.output.split("\n* ")[0].strip()
    data = json.loads(json_text)
    assert "notes" in data
    assert "result_count" in data


def test_note_show_json_includes_body(runner, vault_env):
    result = runner.invoke(main, ["note", "show", "mvcc"])
    assert result.exit_code == 0
    json_text = result.output.split("\n* ")[0].strip()
    data = json.loads(json_text)
    if data["notes"]:
        assert "body" in data["notes"][0]
        assert isinstance(data["notes"][0]["body"], str)


def test_note_show_json_includes_backlinks(runner, vault_env):
    result = runner.invoke(main, ["note", "show", "mvcc"])
    assert result.exit_code == 0
    json_text = result.output.split("\n* ")[0].strip()
    data = json.loads(json_text)
    if data["notes"]:
        assert "backlinks" in data["notes"][0]
        assert isinstance(data["notes"][0]["backlinks"], list)


def test_note_show_format_md(runner, vault_env):
    """pkm note show --format md outputs markdown content."""
    result = runner.invoke(main, ["note", "show", "mvcc", "--format", "md"])
    assert result.exit_code == 0
    assert "{" not in result.output[:5]  # Not JSON start


def test_note_show_top_n(runner, vault_env):
    """pkm note show --top 1 returns at most 1 note."""
    result = runner.invoke(main, ["note", "show", "2026", "--top", "1"])
    assert result.exit_code == 0
    json_text = result.output.split("\n* ")[0].strip()
    data = json.loads(json_text)
    assert len(data["notes"]) <= 1


def test_note_show_no_interactive_prompt(runner, vault_env):
    """note show must never call click.prompt — safe for non-TTY agents."""
    from pkm.commands import notes as notes_mod

    assert not hasattr(notes_mod, "_select_note") or not callable(
        getattr(notes_mod, "_select_note", None)
    )


def test_note_show_json_action_guide(runner, vault_env):
    result = runner.invoke(main, ["note", "show", "mvcc"])
    assert result.exit_code == 0
    assert "pkm note edit" in result.output or "pkm search" in result.output
