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
            return np.array(
                [[hash(t) % 100 / 100.0] * 384 for t in texts_list]
            )

    monkeypatch.setattr("pkm.search_engine.HAS_TRANSFORMERS", True)
    monkeypatch.setattr("pkm.search_engine.SentenceTransformer", lambda name: FakeModel())


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

    result = cli_runner("search", "MVCC 동시성")
    assert result.exit_code == 0, result.output

    # Should show a table with at least rank column
    assert "#" in result.output or "rank" in result.output.lower() or "Title" in result.output


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
    assert "Warning" in result.output or "out of date" in result.output or "stale" in result.output.lower()
