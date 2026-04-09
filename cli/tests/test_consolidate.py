"""Tests for pkm consolidate command."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from click.testing import CliRunner

from pkm.commands.consolidate import (
    consolidate,
    _parse_frontmatter,
    _set_frontmatter_field,
)
from pkm.config import VaultConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vault(tmp_path: Path) -> VaultConfig:
    """Create a minimal vault structure and return VaultConfig."""
    vault_path = tmp_path / "vault"
    (vault_path / "daily").mkdir(parents=True)
    return VaultConfig(name="test", path=vault_path)


def _write_daily(vault: VaultConfig, date_str: str, content: str) -> Path:
    path = vault.daily_dir / f"{date_str}.md"
    path.write_text(content, encoding="utf-8")
    return path


def _invoke(vault: VaultConfig, *args: str):
    runner = CliRunner()
    obj = {"vault": vault}
    return runner.invoke(consolidate, list(args), obj=obj)


# ---------------------------------------------------------------------------
# _parse_frontmatter
# ---------------------------------------------------------------------------


def test_parse_frontmatter_no_frontmatter():
    fm = _parse_frontmatter("just plain text")
    assert fm == {}


def test_parse_frontmatter_malformed():
    fm = _parse_frontmatter("---\n: bad: yaml: :\n---\nbody")
    assert isinstance(fm, dict)


def test_parse_frontmatter_consolidated_true():
    text = "---\nconsolidated: true\n---\n"
    fm = _parse_frontmatter(text)
    assert fm.get("consolidated") is True


def test_parse_frontmatter_tags():
    text = "---\ntags:\n  - daily-notes\n---\n\nbody"
    fm = _parse_frontmatter(text)
    assert fm["tags"] == ["daily-notes"]


# ---------------------------------------------------------------------------
# _set_frontmatter_field
# ---------------------------------------------------------------------------


def test_set_frontmatter_field_adds_key():
    text = "---\ntags:\n  - foo\n---\n\nbody"
    result = _set_frontmatter_field(text, "consolidated", True)
    fm = _parse_frontmatter(result)
    assert fm["consolidated"] is True
    assert fm["tags"] == ["foo"]
    assert "body" in result


def test_set_frontmatter_field_preserves_other_fields():
    text = "---\ntags:\n  - daily-notes\n---\n\nbody here"
    result = _set_frontmatter_field(text, "consolidated", True)
    fm = _parse_frontmatter(result)
    assert fm["tags"] == ["daily-notes"]
    assert fm["consolidated"] is True


def test_set_frontmatter_field_no_frontmatter():
    text = "plain body"
    result = _set_frontmatter_field(text, "consolidated", True)
    fm = _parse_frontmatter(result)
    assert fm["consolidated"] is True
    assert "plain body" in result


# ---------------------------------------------------------------------------
# consolidate (list candidates)
# ---------------------------------------------------------------------------


def test_consolidate_lists_past_notes(tmp_path):
    vault = _make_vault(tmp_path)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _write_daily(vault, yesterday, "---\ntags:\n  - daily-notes\n---\n\n- entry one\n")

    result = _invoke(vault)
    assert result.exit_code == 0
    assert yesterday in result.output


def test_consolidate_excludes_today(tmp_path):
    vault = _make_vault(tmp_path)
    today = date.today().isoformat()
    _write_daily(vault, today, "---\ntags:\n  - daily-notes\n---\n\n- entry\n")

    result = _invoke(vault)
    assert result.exit_code == 0
    assert today not in result.output


def test_consolidate_excludes_already_consolidated(tmp_path):
    vault = _make_vault(tmp_path)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _write_daily(vault, yesterday, "---\nconsolidated: true\n---\n\n- entry\n")

    result = _invoke(vault)
    assert result.exit_code == 0
    assert yesterday not in result.output
    assert "No daily notes eligible" in result.output


def test_consolidate_no_daily_dir(tmp_path):
    vault_path = tmp_path / "empty_vault"
    vault_path.mkdir()
    vault = VaultConfig(name="empty", path=vault_path)

    result = _invoke(vault)
    assert result.exit_code == 0
    assert "No daily/ directory found" in result.output


# ---------------------------------------------------------------------------
# consolidate mark
# ---------------------------------------------------------------------------


def test_consolidate_mark_sets_consolidated(tmp_path):
    vault = _make_vault(tmp_path)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    note_path = _write_daily(
        vault, yesterday, "---\ntags:\n  - daily-notes\n---\n\n- entry\n"
    )

    result = _invoke(vault, "mark", yesterday)
    assert result.exit_code == 0
    assert "Marked as consolidated" in result.output

    fm = _parse_frontmatter(note_path.read_text(encoding="utf-8"))
    assert fm.get("consolidated") is True


def test_consolidate_mark_idempotent(tmp_path):
    vault = _make_vault(tmp_path)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _write_daily(vault, yesterday, "---\nconsolidated: true\n---\n\n- entry\n")

    result = _invoke(vault, "mark", yesterday)
    assert result.exit_code == 0
    assert "Already consolidated" in result.output


def test_consolidate_mark_today_raises(tmp_path):
    vault = _make_vault(tmp_path)
    today = date.today().isoformat()
    _write_daily(vault, today, "---\ntags:\n  - daily-notes\n---\n\n- entry\n")

    result = _invoke(vault, "mark", today)
    assert result.exit_code != 0
    assert "still in use" in result.output


def test_consolidate_mark_missing_file(tmp_path):
    vault = _make_vault(tmp_path)

    result = _invoke(vault, "mark", "2020-01-01")
    assert result.exit_code != 0
    assert "not found" in result.output
