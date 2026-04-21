"""Tests for daemon auto-consolidation on shutdown."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig
from pkm.daemon import _on_shutdown
from pkm.commands.consolidate import _parse_frontmatter


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def vault_env(tmp_vault: VaultConfig, monkeypatch):
    monkeypatch.setenv("PKM_VAULTS_ROOT", str(tmp_vault.path.parent))
    monkeypatch.setenv("PKM_DEFAULT_VAULT", tmp_vault.name)
    return tmp_vault


@pytest.fixture
def clean_vault(tmp_path: Path) -> VaultConfig:
    """A vault with NO pre-existing daily notes (unlike tmp_vault from conftest)."""
    vault_path = tmp_path / "clean-vault"
    for d in ("daily", "notes", "tags", ".pkm"):
        (vault_path / d).mkdir(parents=True)
    return VaultConfig(name="clean-vault", path=vault_path)


@pytest.fixture
def vault_with_dailies(clean_vault: VaultConfig) -> VaultConfig:
    """Clean vault with exactly 3 unconsolidated daily notes."""
    for i in range(1, 4):
        d = (date.today() - timedelta(days=i)).isoformat()
        (clean_vault.daily_dir / f"{d}.md").write_text(
            f"---\nid: {d}\ntags:\n  - daily-notes\n---\n- [{9 + i}:00] Work item {i}\n",
            encoding="utf-8",
        )
    return clean_vault


class TestOnShutdown:
    def test_auto_consolidates_eligible_dailies(self, vault_with_dailies):
        """_on_shutdown should mark eligible daily notes as consolidated."""
        with patch(
            "pkm.config.discover_vaults",
            return_value={"v": vault_with_dailies},
        ):
            _on_shutdown()

        for i in range(1, 4):
            d = (date.today() - timedelta(days=i)).isoformat()
            text = (vault_with_dailies.daily_dir / f"{d}.md").read_text(
                encoding="utf-8"
            )
            fm = _parse_frontmatter(text)
            assert fm.get("consolidated") is True, f"{d} should be consolidated"

    def test_writes_zettel_pending_signal(self, vault_with_dailies):
        """Should write .pkm/zettel-pending with marked count."""
        with patch(
            "pkm.config.discover_vaults",
            return_value={"v": vault_with_dailies},
        ):
            _on_shutdown()

        signal_path = vault_with_dailies.pkm_dir / "zettel-pending"
        assert signal_path.exists()
        sig = json.loads(signal_path.read_text(encoding="utf-8"))
        assert sig["marked"] == 3
        assert "timestamp" in sig

    def test_skips_today(self, vault_with_dailies):
        """Today's daily should NOT be consolidated."""
        today = date.today().isoformat()
        (vault_with_dailies.daily_dir / f"{today}.md").write_text(
            f"---\nid: {today}\ntags:\n  - daily-notes\n---\n- [09:00] Today\n",
            encoding="utf-8",
        )

        with patch(
            "pkm.config.discover_vaults",
            return_value={"v": vault_with_dailies},
        ):
            _on_shutdown()

        today_text = (vault_with_dailies.daily_dir / f"{today}.md").read_text(
            encoding="utf-8"
        )
        assert _parse_frontmatter(today_text).get("consolidated") is not True

    def test_skips_already_consolidated(self, vault_with_dailies):
        """Already-consolidated notes should not be double-marked."""
        d = (date.today() - timedelta(days=1)).isoformat()
        (vault_with_dailies.daily_dir / f"{d}.md").write_text(
            f"---\nid: {d}\nconsolidated: true\ntags:\n  - daily-notes\n---\n- Done\n",
            encoding="utf-8",
        )

        with patch(
            "pkm.config.discover_vaults",
            return_value={"v": vault_with_dailies},
        ):
            _on_shutdown()

        signal_path = vault_with_dailies.pkm_dir / "zettel-pending"
        sig = json.loads(signal_path.read_text(encoding="utf-8"))
        assert sig["marked"] == 2  # 3 total minus 1 already consolidated

    def test_no_signal_when_nothing_to_mark(self, clean_vault):
        """No signal file if no eligible dailies exist."""
        with patch(
            "pkm.config.discover_vaults",
            return_value={"v": clean_vault},
        ):
            _on_shutdown()

        signal_path = clean_vault.pkm_dir / "zettel-pending"
        assert not signal_path.exists()


class TestSessionStartZettelPending:
    def test_session_start_shows_zettel_pending(self, runner, vault_env):
        """session-start should display zettel-loop suggestion when signal exists."""
        signal_path = vault_env.pkm_dir / "zettel-pending"
        signal_path.write_text(
            json.dumps({"marked": 5, "timestamp": "2026-04-14T00:00:00Z"}),
            encoding="utf-8",
        )

        result = runner.invoke(main, ["hook", "run", "session-start"])

        assert result.exit_code == 0
        assert "Zettel Loop Ready" in result.output
        assert "5 daily note(s)" in result.output
        assert "zettel-loop" in result.output
        # Signal should be consumed
        assert not signal_path.exists()

    def test_session_start_no_signal_no_zettel(self, runner, vault_env):
        """session-start should not mention zettel-loop without signal."""
        result = runner.invoke(main, ["hook", "run", "session-start"])

        assert result.exit_code == 0
        assert "Zettel Loop Ready" not in result.output
