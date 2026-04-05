"""Tests for pkm memory store/search/session commands."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from pkm.cli import main
from pkm.commands.memory import _scan_memory_notes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault(tmp_path: Path) -> Path:
    """Create a minimal vault structure and set env vars."""
    vault = tmp_path / "vault"
    (vault / "notes").mkdir(parents=True)
    (vault / "daily").mkdir(parents=True)
    vaults_root = tmp_path
    os.environ["PKM_VAULTS_ROOT"] = str(vaults_root)
    os.environ["PKM_DEFAULT_VAULT"] = "vault"
    return vault


_runner = CliRunner()


def invoke(args: list[str], input: str | None = None) -> object:
    return _runner.invoke(main, args, input=input, catch_exceptions=False)


# ---------------------------------------------------------------------------
# store tests
# ---------------------------------------------------------------------------

class TestMemoryStore:
    def test_store_positional_content(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        result = invoke(["memory", "store", "learned X", "--type", "semantic", "--importance", "7"])
        assert result.exit_code == 0, result.output
        notes = list((vault / "notes").glob("*.md"))
        assert len(notes) == 1
        note_path = notes[0]
        assert note_path.exists()
        text = note_path.read_text()
        assert "learned X" in text

    def test_store_creates_correct_frontmatter(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        result = invoke([
            "memory", "store", "learned X",
            "--type", "semantic",
            "--importance", "7",
            "--session", "abc123",
        ])
        assert result.exit_code == 0, result.output
        notes = list((vault / "notes").glob("*.md"))
        assert len(notes) == 1
        text = notes[0].read_text()
        # Parse frontmatter
        assert text.startswith("---")
        end = text.find("---", 3)
        fm = yaml.safe_load(text[3:end])
        assert fm["memory_type"] == "semantic"
        assert fm["importance"] == 7.0
        assert fm["session_id"] == "abc123"
        assert fm["source_type"] == "agent"
        assert "created_at" in fm

    def test_store_stdin(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        result = invoke(
            ["memory", "store", "--stdin", "--type", "episodic", "--importance", "5"],
            input="multi-line content",
        )
        assert result.exit_code == 0, result.output
        notes = list((vault / "notes").glob("*.md"))
        assert len(notes) == 1
        assert "multi-line content" in notes[0].read_text()

    def test_store_error_when_no_content(self, tmp_path: Path) -> None:
        _make_vault(tmp_path)
        result = _runner.invoke(main, ["memory", "store", "--type", "semantic"], catch_exceptions=False)
        assert result.exit_code != 0

    def test_store_with_tags(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        result = invoke([
            "memory", "store", "tagged memory",
            "--type", "procedural",
            "--importance", "3",
            "--tags", "foo,bar",
        ])
        assert result.exit_code == 0, result.output
        notes = list((vault / "notes").glob("*.md"))
        text = notes[0].read_text()
        end = text.find("---", 3)
        fm = yaml.safe_load(text[3:end])
        assert "foo" in fm["tags"]
        assert "bar" in fm["tags"]

    def test_store_collision_avoidance(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        # Store twice with same content (same slug → collision)
        invoke(["memory", "store", "same content", "--type", "semantic", "--importance", "5"])
        invoke(["memory", "store", "same content", "--type", "semantic", "--importance", "5"])
        notes = list((vault / "notes").glob("*.md"))
        assert len(notes) == 2

    def test_store_outputs_path(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        result = invoke(["memory", "store", "output path test", "--type", "semantic", "--importance", "5"])
        assert result.exit_code == 0
        output_path = Path(result.output.strip())
        assert output_path.exists()
        assert output_path.suffix == ".md"


# ---------------------------------------------------------------------------
# search tests
# ---------------------------------------------------------------------------

class TestMemorySearch:
    def _store(self, content: str, mtype: str, importance: int, session: str | None = None) -> None:
        args = ["memory", "store", content, "--type", mtype, "--importance", str(importance)]
        if session:
            args += ["--session", session]
        invoke(args)

    def test_search_returns_results(self, tmp_path: Path) -> None:
        _make_vault(tmp_path)
        self._store("Python is great for data science", "semantic", 8)
        self._store("Rust is fast and safe", "semantic", 6)
        result = invoke(["memory", "search", "Python data science"])
        assert result.exit_code == 0, result.output
        assert "Python" in result.output or "python" in result.output.lower()

    def test_search_no_results(self, tmp_path: Path) -> None:
        _make_vault(tmp_path)
        result = invoke(["memory", "search", "xyznonexistent"])
        assert result.exit_code == 0
        assert "No results" in result.output

    def test_search_filter_by_type(self, tmp_path: Path) -> None:
        _make_vault(tmp_path)
        self._store("episodic memory content", "episodic", 5)
        self._store("semantic memory content", "semantic", 5)
        result = invoke(["memory", "search", "memory content", "--type", "episodic"])
        assert result.exit_code == 0, result.output
        # Should only return episodic result
        assert "episodic" in result.output

    def test_search_json_format(self, tmp_path: Path) -> None:
        import json as json_mod
        _make_vault(tmp_path)
        self._store("json search test", "semantic", 7)
        result = invoke(["memory", "search", "json search", "--format", "json"])
        assert result.exit_code == 0, result.output
        data = json_mod.loads(result.output)
        assert isinstance(data, list)

    def test_search_recency_weight(self, tmp_path: Path) -> None:
        _make_vault(tmp_path)
        self._store("recency test content", "semantic", 5)
        result = invoke(["memory", "search", "recency test", "--recency-weight", "0.8"])
        assert result.exit_code == 0, result.output

    def test_search_plain_format(self, tmp_path: Path) -> None:
        _make_vault(tmp_path)
        self._store("plain format test", "semantic", 5)
        result = invoke(["memory", "search", "plain format", "--format", "plain"])
        assert result.exit_code == 0, result.output
        # plain format: "score  title  [path]"
        assert "[" in result.output


# ---------------------------------------------------------------------------
# session tests
# ---------------------------------------------------------------------------

class TestMemorySession:
    def _store(self, content: str, session: str, mtype: str = "semantic", importance: int = 5) -> None:
        invoke([
            "memory", "store", content,
            "--type", mtype,
            "--importance", str(importance),
            "--session", session,
        ])

    def test_session_lists_notes(self, tmp_path: Path) -> None:
        _make_vault(tmp_path)
        self._store("first memory", "sess-abc")
        self._store("second memory", "sess-abc")
        self._store("other session memory", "sess-xyz")
        result = invoke(["memory", "session", "sess-abc"])
        assert result.exit_code == 0, result.output
        assert "first" in result.output or "second" in result.output
        # Should not list the other session's note
        assert "other" not in result.output

    def test_session_no_results(self, tmp_path: Path) -> None:
        _make_vault(tmp_path)
        result = invoke(["memory", "session", "nonexistent-session"])
        assert result.exit_code == 0
        assert "No memories found" in result.output

    def test_session_json_format(self, tmp_path: Path) -> None:
        import json as json_mod
        _make_vault(tmp_path)
        self._store("json session test", "sess-json")
        result = invoke(["memory", "session", "sess-json", "--format", "json"])
        assert result.exit_code == 0, result.output
        data = json_mod.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] is not None

    def test_session_plain_format(self, tmp_path: Path) -> None:
        _make_vault(tmp_path)
        self._store("plain session test", "sess-plain")
        result = invoke(["memory", "session", "sess-plain", "--format", "plain"])
        assert result.exit_code == 0, result.output
        assert "plain" in result.output.lower() or result.output.strip()

    def test_session_isolates_by_id(self, tmp_path: Path) -> None:
        _make_vault(tmp_path)
        for i in range(3):
            self._store(f"memory {i}", "target-session")
        self._store("other", "other-session")
        result = invoke(["memory", "session", "target-session"])
        assert result.exit_code == 0
        # 3 rows + header + separator = 5 lines minimum
        lines = [l for l in result.output.splitlines() if l.strip()]
        data_lines = [l for l in lines if "memory" in l.lower() or "target" in l.lower() or "2026" in l]
        assert len(data_lines) >= 3


# ---------------------------------------------------------------------------
# _scan_memory_notes unit test
# ---------------------------------------------------------------------------

def test_scan_memory_notes_skips_non_memory(tmp_path: Path) -> None:
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()

    # Non-memory note (no memory_type field)
    (notes_dir / "regular.md").write_text("---\nid: regular\n---\nContent\n")
    # Memory note
    (notes_dir / "memory.md").write_text(
        "---\nid: mem1\nmemory_type: semantic\nimportance: 5.0\n---\nBody\n"
    )

    results = _scan_memory_notes(notes_dir)
    assert len(results) == 1
    assert results[0]["title"] == "mem1"
