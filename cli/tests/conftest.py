"""Shared test fixtures for PKM CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pkm.config import VaultConfig


@pytest.fixture
def tmp_vault(tmp_path: Path) -> VaultConfig:
    """Create a temporary vault with standard structure and sample files."""
    vault_path = tmp_path / "test-vault"
    for d in (
        "daily",
        "notes",
        "tags",
        "tasks",
        "tasks/archive",
        "data",
        ".pkm",
        ".pkm/artifacts",
    ):
        (vault_path / d).mkdir(parents=True)

    # Sample daily note
    daily = vault_path / "daily" / "2026-04-01.md"
    daily.write_text(
        "---\nid: 2026-04-01\naliases: []\ntags:\n  - daily-notes\n---\n"
        "- [09:00] Today task planning\n- [14:30] MVCC concept study\n\n"
        "## TODO\n- [09:00] Write documentation\n",
        encoding="utf-8",
    )

    daily2 = vault_path / "daily" / "2026-04-02.md"
    daily2.write_text(
        "---\nid: 2026-04-02\naliases: []\ntags:\n  - daily-notes\n---\n"
        "- [10:00] Additional MVCC study\n\n## TODO\n",
        encoding="utf-8",
    )

    # Sample notes with wikilinks
    note_a = vault_path / "notes" / "2026-04-01-mvcc.md"
    note_a.write_text(
        "---\nid: 2026-04-01-mvcc\naliases:\n  - MVCC\ntags:\n  - database\n  - postgresql\n---\n\n"
        "MVCC is a concurrency control technique.\n\nRelated: [[2026-04-01]], [[database-isolation]]\n",
        encoding="utf-8",
    )

    note_b = vault_path / "notes" / "database-isolation.md"
    note_b.write_text(
        "---\nid: database-isolation\naliases: []\ntags:\n  - database\n---\n\n"
        "Description of isolation levels.\n\nRelated: [[2026-04-01-mvcc]]\n",
        encoding="utf-8",
    )

    # Note with description (for backlink display testing)
    note_desc = vault_path / "notes" / "concurrency-note.md"
    note_desc.write_text(
        "---\nid: concurrency-note\naliases: []\ntags:\n  - database\n"
        "description: Concurrency control technique comparison note\n---\n\n"
        "Compares various concurrency control techniques.\n\nRelated: [[2026-04-01-mvcc]]\n",
        encoding="utf-8",
    )

    # Orphan note (no links in or out)
    orphan = vault_path / "notes" / "isolated-note.md"
    orphan.write_text(
        "---\nid: isolated-note\naliases: []\ntags:\n  - untagged\n---\n\n"
        "A note with no connections.\n",
        encoding="utf-8",
    )

    # Note without tags (for capture-triage testing)
    no_tags = vault_path / "notes" / "untagged-note.md"
    no_tags.write_text(
        "---\nid: untagged-note\naliases: []\ntags: []\n---\n\nA note with no tags.\n",
        encoding="utf-8",
    )

    # Task file
    ongoing = vault_path / "tasks" / "ongoing.md"
    ongoing.write_text(
        "---\nid: ongoing-tasks\ntags:\n  - tasks\n---\n\n"
        "# In Progress\n\n## 🔴 In Progress (WIP)\n\n## 🟡 Planned (TODO)\n\n"
        "## ✅ Completed This Week\n\n## ⏸ On Hold\n",
        encoding="utf-8",
    )

    return VaultConfig(name="test-vault", path=vault_path)


@pytest.fixture
def vault_config(tmp_vault: VaultConfig) -> VaultConfig:
    """Alias for tmp_vault for readability."""
    return tmp_vault


@pytest.fixture(autouse=True)
def disable_auto_vault(monkeypatch):
    """Disable auto git project and local config mapping during tests."""
    from pkm import config

    monkeypatch.setattr(config, "get_git_vault_name", lambda: None)
    monkeypatch.setattr(config, "get_local_config_vault", lambda: None)
