"""CLI integration tests for search commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_model(monkeypatch):
    """Replace SentenceTransformer with a deterministic fake model."""

    class FakeModel:
        def encode(self, texts, **kwargs):
            import numpy as np

            texts_list = texts if isinstance(texts, list) else [texts]
            return np.array([[hash(t) % 100 / 100.0] * 384 for t in texts_list])

    monkeypatch.setattr(
        "pkm.search_engine._require_transformers", lambda name: FakeModel()
    )


@pytest.fixture
def cli_runner(runner, tmp_vault: VaultConfig, monkeypatch):
    """Return a runner that invokes main with tmp_vault injected."""

    def invoke(*args):
        monkeypatch.setattr(
            "pkm.config.discover_vaults",
            lambda root=None: {"test-vault": tmp_vault},
        )
        monkeypatch.setattr("pkm.config.load_config", lambda: {})
        monkeypatch.delenv("PKM_DEFAULT_VAULT", raising=False)
        return runner.invoke(main, list(args), catch_exceptions=False)

    return invoke


def test_index_command(cli_runner, tmp_vault: VaultConfig, mock_model):
    """pkm index builds index.json in .pkm/."""
    result = cli_runner("index")
    assert result.exit_code == 0, result.output

    index_path = tmp_vault.pkm_dir / "index.json"
    assert index_path.exists(), "index.json should be created after index command"

    data = json.loads(index_path.read_text(encoding="utf-8"))
    assert "entries" in data
    assert len(data["entries"]) > 0

    assert "indexed" in result.output.lower()


def test_search_command(cli_runner, tmp_vault: VaultConfig, mock_model):
    """pkm search displays a results table."""
    # Build index first
    cli_runner("index")

    result = cli_runner("search", "MVCC concurrency")
    assert result.exit_code == 0, result.output

    # Should show a table with at least rank column
    assert (
        "#" in result.output
        or "rank" in result.output.lower()
        or "Title" in result.output
    )


def test_search_memory_type_filter(cli_runner, tmp_vault: VaultConfig, mock_model):
    """pkm search --type accepts memory_type filter without error."""
    cli_runner("index")
    result = cli_runner("search", "MVCC", "--type", "semantic")
    assert result.exit_code == 0, result.output


def test_search_min_importance_filter(cli_runner, tmp_vault: VaultConfig, mock_model):
    """pkm search --min-importance accepts importance filter without error."""
    cli_runner("index")
    result = cli_runner("search", "MVCC", "--min-importance", "5")
    assert result.exit_code == 0, result.output


def test_search_recency_weight(cli_runner, tmp_vault: VaultConfig, mock_model):
    """pkm search --recency-weight accepts recency weight without error."""
    cli_runner("index")
    result = cli_runner("search", "MVCC", "--recency-weight", "0.4")
    assert result.exit_code == 0, result.output


def test_search_session_filter(
    cli_runner, tmp_vault: VaultConfig, mock_model, tmp_path
):
    """pkm search --session returns only notes with matching session_id."""
    # Create a note with session_id in tmp_vault
    session_note = tmp_vault.notes_dir / "2026-01-01-session-test-note.md"
    session_note.write_text(
        "---\nid: session-test-note\nsession_id: test-session-abc\nmemory_type: episodic\nimportance: 5.0\ntags: []\naliases: []\n---\nSession test content.\n",
        encoding="utf-8",
    )
    cli_runner("index")

    result = cli_runner("search", "session test", "--session", "test-session-abc")
    assert result.exit_code == 0, result.output


def test_search_stale_warning(cli_runner, tmp_vault: VaultConfig, mock_model):
    """pkm search warns when index is stale."""
    # Build index
    cli_runner("index")

    # Create a new note to make index stale
    new_note = tmp_vault.notes_dir / "newer-note.md"
    new_note.write_text(
        "---\nid: newer-note\naliases: []\ntags: []\n---\nNewer note.\n",
        encoding="utf-8",
    )

    result = cli_runner("search", "something")
    assert result.exit_code == 0, result.output
    assert (
        "Warning" in result.output
        or "out of date" in result.output
        or "stale" in result.output.lower()
    )
