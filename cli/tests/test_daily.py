"""Tests for daily note commands."""

from __future__ import annotations

import re
from datetime import datetime

import pytest
from click.testing import CliRunner

from pkm.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cli_runner(runner, tmp_vault, monkeypatch):
    """Return a runner that invokes main with the tmp_vault injected."""

    def invoke(*args, input=None):
        monkeypatch.setattr(
            "pkm.config.discover_vaults",
            lambda root=None: {"test-vault": tmp_vault},
        )
        monkeypatch.setattr("pkm.config.load_config", lambda: {})
        return runner.invoke(main, list(args), catch_exceptions=False, input=input)

    return invoke


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# daily base command
# ---------------------------------------------------------------------------


def test_daily_creates_note(cli_runner, tmp_vault):
    """daily creates today's note when it doesn't exist."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    assert not note_path.exists()

    result = cli_runner("daily")
    assert result.exit_code == 0

    assert note_path.exists()
    content = note_path.read_text(encoding="utf-8")
    assert f"id: {today_str}" in content
    assert "consolidated: false" in content
    assert "daily-notes" in content
    assert "## Logs" in content
    assert "## TODO" not in content


def test_daily_shows_existing(cli_runner, tmp_vault):
    """daily prints content of an existing today's note."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text("existing content\n", encoding="utf-8")

    result = cli_runner("daily")
    assert result.exit_code == 0
    assert "existing content" in result.output


def test_daily_shows_subnotes_below_main(cli_runner, tmp_vault):
    """pkm daily shows sub-notes below the main note with separators."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text("main content\n", encoding="utf-8")

    sub = tmp_vault.daily_dir / f"{today_str}-meeting.md"
    sub.write_text("sub content\n", encoding="utf-8")

    result = cli_runner("daily")
    assert result.exit_code == 0
    assert "main content" in result.output
    assert "--- meeting ---" in result.output
    assert "sub content" in result.output
    assert result.output.index("main content") < result.output.index("sub content")


def test_daily_no_subnotes_output_unchanged(cli_runner, tmp_vault):
    """pkm daily without sub-notes shows only the main note (no separators)."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text("just main\n", encoding="utf-8")

    result = cli_runner("daily")
    assert result.exit_code == 0
    assert "just main" in result.output
    assert "---" not in result.output


# ---------------------------------------------------------------------------
# daily add
# ---------------------------------------------------------------------------


def test_daily_add(cli_runner, tmp_vault):
    """daily add appends a [hh:mm:ss] timestamped line to the note."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text(
        f"---\nid: {today_str}\nconsolidated: false\naliases: []\ntags:\n- daily-notes\n---\n## Logs\n",
        encoding="utf-8",
    )

    result = cli_runner("daily", "add", "work log entry")
    assert result.exit_code == 0

    content = note_path.read_text(encoding="utf-8")
    assert "work log entry" in content
    # Should contain [HH:MM:SS] timestamp (seconds included)
    assert re.search(r"\[\d{2}:\d{2}:\d{2}\] work log entry", content)


def test_daily_add_no_todo_section(cli_runner, tmp_vault):
    """daily add works when note has no ## TODO section."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text(
        f"---\nid: {today_str}\n---\n## Logs\nlog content\n",
        encoding="utf-8",
    )

    result = cli_runner("daily", "add", "new entry")
    assert result.exit_code == 0

    content = note_path.read_text(encoding="utf-8")
    assert "new entry" in content
    assert re.search(r"\[\d{2}:\d{2}:\d{2}\] new entry", content)


def test_daily_add_creates_note_if_missing(cli_runner, tmp_vault):
    """daily add creates the daily note if it doesn't exist."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    assert not note_path.exists()

    result = cli_runner("daily", "add", "first entry")
    assert result.exit_code == 0

    assert note_path.exists()
    content = note_path.read_text(encoding="utf-8")
    assert "first entry" in content
    assert "## Logs" in content
    assert "consolidated: false" in content


def test_daily_add_appends_multiple_entries(cli_runner, tmp_vault):
    """daily add stacks multiple entries at the end."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text(
        f"---\nid: {today_str}\n---\n## Logs\n",
        encoding="utf-8",
    )

    cli_runner("daily", "add", "entry one")
    cli_runner("daily", "add", "entry two")

    content = note_path.read_text(encoding="utf-8")
    assert "entry one" in content
    assert "entry two" in content
    assert content.index("entry one") < content.index("entry two")


def test_daily_add_no_sub_option(cli_runner, tmp_vault):
    """daily add does not accept --sub option."""
    result = cli_runner("daily", "add", "--sub", "title")
    assert result.exit_code != 0


def test_daily_add_requires_text(cli_runner, tmp_vault):
    """daily add with no arguments fails."""
    result = cli_runner("daily", "add")
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# daily subnote
# ---------------------------------------------------------------------------


def test_daily_subnote_creates_file_and_logs_link(cli_runner, tmp_vault):
    """daily subnote creates the subnote and logs [[wikilink]] in daily note."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text(
        f"---\nid: {today_str}\nconsolidated: false\naliases: []\ntags:\n- daily-notes\n---\n## Logs\n",
        encoding="utf-8",
    )

    result = cli_runner("daily", "subnote", "meeting")
    assert result.exit_code == 0, result.output

    note_id = f"{today_str}-meeting"
    subnote = tmp_vault.daily_dir / f"{note_id}.md"
    assert subnote.exists()

    daily_content = note_path.read_text(encoding="utf-8")
    assert f"[[{note_id}]]" in daily_content
    assert re.search(
        r"\[\d{2}:\d{2}:\d{2}\] \[\[" + re.escape(note_id) + r"\]\]", daily_content
    )
    # Should NOT have "Sub note added" prefix
    assert "Sub note added" not in daily_content


def test_daily_subnote_with_content(cli_runner, tmp_vault):
    """daily subnote --content writes body into the subnote."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text(f"---\nid: {today_str}\n---\n## Logs\n", encoding="utf-8")

    result = cli_runner("daily", "subnote", "ideas", "--content", "# Ideas\n- idea 1")
    assert result.exit_code == 0, result.output

    note_id = f"{today_str}-ideas"
    subnote = tmp_vault.daily_dir / f"{note_id}.md"
    content = subnote.read_text(encoding="utf-8")
    assert "# Ideas" in content
    assert "idea 1" in content


def test_daily_subnote_with_tags(cli_runner, tmp_vault):
    """daily subnote --tags writes tags in subnote frontmatter."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text(f"---\nid: {today_str}\n---\n## Logs\n", encoding="utf-8")

    result = cli_runner("daily", "subnote", "work-item", "--tags", "work,project")
    assert result.exit_code == 0, result.output

    note_id = f"{today_str}-work-item"
    subnote = tmp_vault.daily_dir / f"{note_id}.md"
    content = subnote.read_text(encoding="utf-8")
    assert "work" in content
    assert "project" in content


def test_daily_subnote_with_aliases(cli_runner, tmp_vault):
    """daily subnote --aliases writes aliases in subnote frontmatter."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text(f"---\nid: {today_str}\n---\n## Logs\n", encoding="utf-8")

    result = cli_runner("daily", "subnote", "retro", "--aliases", "Retrospective,Retro")
    assert result.exit_code == 0, result.output

    note_id = f"{today_str}-retro"
    subnote = tmp_vault.daily_dir / f"{note_id}.md"
    content = subnote.read_text(encoding="utf-8")
    assert "Retrospective" in content
    assert "Retro" in content


def test_daily_subnote_stdin(cli_runner, tmp_vault):
    """daily subnote --stdin reads content from stdin."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text(f"---\nid: {today_str}\n---\n## Logs\n", encoding="utf-8")

    result = cli_runner(
        "daily", "subnote", "from-stdin", "--stdin", input="stdin body\n"
    )
    assert result.exit_code == 0, result.output

    note_id = f"{today_str}-from-stdin"
    subnote = tmp_vault.daily_dir / f"{note_id}.md"
    assert subnote.exists()
    assert "stdin body" in subnote.read_text(encoding="utf-8")


def test_daily_subnote_stdin_and_content_error(cli_runner, tmp_vault):
    """daily subnote --stdin and --content together is an error."""
    result = cli_runner("daily", "subnote", "title", "--stdin", "--content", "body")
    assert result.exit_code != 0


def test_daily_subnote_existing_not_overwritten(cli_runner, tmp_vault):
    """daily subnote does not overwrite an existing subnote, only logs link."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text(f"---\nid: {today_str}\n---\n## Logs\n", encoding="utf-8")

    note_id = f"{today_str}-existing"
    existing = tmp_vault.daily_dir / f"{note_id}.md"
    existing.write_text("original content\n", encoding="utf-8")

    result = cli_runner("daily", "subnote", "existing")
    assert result.exit_code == 0, result.output

    assert existing.read_text(encoding="utf-8") == "original content\n"
    assert f"[[{note_id}]]" in note_path.read_text(encoding="utf-8")


def test_daily_subnote_creates_daily_if_missing(cli_runner, tmp_vault):
    """daily subnote creates the daily note if it doesn't exist yet."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    assert not note_path.exists()

    result = cli_runner("daily", "subnote", "init")
    assert result.exit_code == 0, result.output

    assert note_path.exists()
    content = note_path.read_text(encoding="utf-8")
    assert f"[[{today_str}-init]]" in content
    assert "consolidated: false" in content


def test_daily_subnote_spaces_to_hyphens(cli_runner, tmp_vault):
    """daily subnote sanitizes spaces to hyphens in the title."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text(f"---\nid: {today_str}\n---\n## Logs\n", encoding="utf-8")

    result = cli_runner("daily", "subnote", "my idea")
    assert result.exit_code == 0, result.output

    note_id = f"{today_str}-my-idea"
    assert (tmp_vault.daily_dir / f"{note_id}.md").exists()
    assert f"[[{note_id}]]" in note_path.read_text(encoding="utf-8")


def test_daily_subnote_path_traversal_rejected(cli_runner, tmp_vault):
    """daily subnote rejects titles that would escape daily_dir."""
    result = cli_runner("daily", "subnote", "../evil")
    assert result.exit_code == 0  # sanitized, not rejected outright

    created = list(tmp_vault.daily_dir.glob("*.md"))
    # Ensure no file escaped the daily_dir
    for f in created:
        assert str(f.resolve()).startswith(str(tmp_vault.daily_dir.resolve()))


def test_daily_subnote_frontmatter_defaults(cli_runner, tmp_vault):
    """daily subnote with no options creates subnote with empty tags/aliases."""
    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text(f"---\nid: {today_str}\n---\n## Logs\n", encoding="utf-8")

    result = cli_runner("daily", "subnote", "plain")
    assert result.exit_code == 0, result.output

    note_id = f"{today_str}-plain"
    content = (tmp_vault.daily_dir / f"{note_id}.md").read_text(encoding="utf-8")
    assert f"id: {note_id}" in content
    assert "aliases:" in content
    assert "tags:" in content


# ---------------------------------------------------------------------------
# daily edit
# ---------------------------------------------------------------------------


class _FakeProc:
    returncode = 0


def _fake_run(calls=None):
    def _run(args):
        if calls is not None:
            calls.append(args)
        return _FakeProc()

    return _run


def test_daily_edit_opens_today_note(cli_runner, tmp_vault, monkeypatch):
    """daily edit opens today's daily note in editor."""
    calls = []
    monkeypatch.setattr(
        "pkm.commands.daily.load_config", lambda: {"defaults": {"editor": "vim"}}
    )
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", _fake_run(calls))

    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    note_path.write_text("existing\n", encoding="utf-8")

    result = cli_runner("daily", "edit")
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert calls[0][0] == "vim"
    assert today_str in calls[0][-1]


def test_daily_edit_creates_note_if_missing(cli_runner, tmp_vault, monkeypatch):
    """daily edit creates the daily note if it doesn't exist yet."""
    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {})
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", _fake_run())

    today_str = today()
    note_path = tmp_vault.daily_dir / f"{today_str}.md"
    assert not note_path.exists()

    result = cli_runner("daily", "edit")
    assert result.exit_code == 0, result.output
    assert note_path.exists()
    content = note_path.read_text(encoding="utf-8")
    assert "## Logs" in content
    assert "consolidated: false" in content
    assert "## TODO" not in content


def test_daily_edit_editor_from_env_visual(cli_runner, tmp_vault, monkeypatch):
    """Editor falls back to $VISUAL when config has no editor."""
    calls = []
    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {})
    monkeypatch.setenv("VISUAL", "emacs")
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", _fake_run(calls))

    result = cli_runner("daily", "edit")
    assert result.exit_code == 0
    assert calls[0][0] == "emacs"


def test_daily_edit_editor_fallback_nano(cli_runner, tmp_vault, monkeypatch):
    """Editor falls back to nano when nothing is configured."""
    calls = []
    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {})
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", _fake_run(calls))

    result = cli_runner("daily", "edit")
    assert result.exit_code == 0
    assert calls[0][0] == "nano"


def test_daily_edit_nonzero_returncode_warns(cli_runner, tmp_vault, monkeypatch):
    """daily edit warns user when editor exits with non-zero code."""

    class _FailProc:
        returncode = 1

    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {})
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", lambda args: _FailProc())

    result = cli_runner("daily", "edit")
    assert result.exit_code == 0, result.output
    assert "1" in result.output


def test_daily_edit_no_sub_option(cli_runner, tmp_vault, monkeypatch):
    """daily edit does not accept --sub option."""
    monkeypatch.setattr("pkm.commands.daily.load_config", lambda: {})
    monkeypatch.setattr("pkm.commands.daily.subprocess.run", _fake_run())
    result = cli_runner("daily", "edit", "--sub")
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# daily todo removed
# ---------------------------------------------------------------------------


def test_daily_todo_command_removed(cli_runner, tmp_vault):
    """daily todo command no longer exists."""
    result = cli_runner("daily", "todo", "some item")
    assert result.exit_code != 0
