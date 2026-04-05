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
        "- [09:00] 오늘 할 일 정리\n- [14:30] MVCC 개념 학습\n\n"
        "## TODO\n- [09:00] 문서 작성\n",
        encoding="utf-8",
    )

    daily2 = vault_path / "daily" / "2026-04-02.md"
    daily2.write_text(
        "---\nid: 2026-04-02\naliases: []\ntags:\n  - daily-notes\n---\n"
        "- [10:00] MVCC 추가 학습\n\n## TODO\n",
        encoding="utf-8",
    )

    # Sample notes with wikilinks
    note_a = vault_path / "notes" / "2026-04-01-mvcc.md"
    note_a.write_text(
        "---\nid: 2026-04-01-mvcc\naliases:\n  - MVCC\ntags:\n  - database\n  - postgresql\n---\n\n"
        "MVCC는 동시성 제어 기법이다.\n\n관련: [[2026-04-01]], [[database-isolation]]\n",
        encoding="utf-8",
    )

    note_b = vault_path / "notes" / "database-isolation.md"
    note_b.write_text(
        "---\nid: database-isolation\naliases: []\ntags:\n  - database\n---\n\n"
        "격리 수준에 대한 설명.\n\n관련: [[2026-04-01-mvcc]]\n",
        encoding="utf-8",
    )

    # Orphan note (no links in or out)
    orphan = vault_path / "notes" / "고립된-노트.md"
    orphan.write_text(
        "---\nid: 고립된-노트\naliases: []\ntags:\n  - 미분류\n---\n\n"
        "아무 연결도 없는 노트.\n",
        encoding="utf-8",
    )

    # Note without tags (for capture-triage testing)
    no_tags = vault_path / "notes" / "untagged-note.md"
    no_tags.write_text(
        "---\nid: untagged-note\naliases: []\ntags: []\n---\n\n태그가 없는 노트.\n",
        encoding="utf-8",
    )

    # Task file
    ongoing = vault_path / "tasks" / "ongoing.md"
    ongoing.write_text(
        "---\nid: ongoing-tasks\ntags:\n  - tasks\n---\n\n"
        "# 진행 중인 일\n\n## 🔴 진행 중 (WIP)\n\n## 🟡 예정 (TODO)\n\n"
        "## ✅ 이번 주 완료\n\n## ⏸ 보류\n",
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

    monkeypatch.setattr(config, "get_git_project_name", lambda: None)
    monkeypatch.setattr(config, "get_local_config_vault", lambda: None)
