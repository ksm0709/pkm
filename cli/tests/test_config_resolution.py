"""Scenario tests for vault and web configuration resolution."""

from __future__ import annotations

from pathlib import Path

import click
import pytest

from pkm import config
from pkm.config import VaultConfig


ORIGINAL_GET_LOCAL_CONFIG_VAULT = config.get_local_config_vault


def _make_vault(root: Path, name: str, marker: str = "notes") -> VaultConfig:
    path = root / name
    (path / marker).mkdir(parents=True)
    return VaultConfig(name=name, path=path)


def test_vault_config_exposes_standard_layout_paths(tmp_path) -> None:
    """VaultConfig path properties all resolve relative to the vault root."""
    vault = VaultConfig(name="v", path=tmp_path / "vault")

    assert vault.daily_dir == vault.path / "daily"
    assert vault.notes_dir == vault.path / "notes"
    assert vault.tags_dir == vault.path / "tags"
    assert vault.data_dir == vault.path / "data"
    assert vault.pkm_dir == vault.path / ".pkm"
    assert vault.artifacts_dir == vault.path / ".pkm" / "artifacts"
    assert vault.graph_path == vault.path / ".pkm" / "graph.json"
    assert vault.graph_enriched_path == vault.path / ".pkm" / "graph_enriched.json"


def test_discover_vaults_filters_hidden_and_non_vault_dirs(tmp_path) -> None:
    """Vault discovery includes daily/notes roots and ignores hidden/non-vault dirs."""
    _make_vault(tmp_path, "daily-vault", marker="daily")
    _make_vault(tmp_path, "notes-vault", marker="notes")
    (tmp_path / ".hidden" / "notes").mkdir(parents=True)
    (tmp_path / "plain-dir").mkdir()
    (tmp_path / "file.txt").write_text("not a dir", encoding="utf-8")

    vaults = config.discover_vaults(tmp_path)

    assert list(vaults) == ["daily-vault", "notes-vault"]
    assert vaults["daily-vault"].daily_dir.is_dir()
    assert vaults["notes-vault"].notes_dir.is_dir()
    assert config.discover_vaults(tmp_path / "missing") == {}


def test_get_vaults_root_prefers_env(monkeypatch, tmp_path) -> None:
    """PKM_VAULTS_ROOT overrides the default vault root."""
    monkeypatch.setenv("PKM_VAULTS_ROOT", str(tmp_path / "vaults"))
    assert config.get_vaults_root() == tmp_path / "vaults"


def test_local_config_resolver_reads_toml_and_legacy_plain_text(
    monkeypatch, tmp_path
) -> None:
    """Local .pkm discovery walks parents and supports TOML plus plain text formats."""
    project = tmp_path / "project"
    child = project / "nested" / "child"
    child.mkdir(parents=True)
    (project / ".pkm").write_text(
        '[defaults]\nvault = "toml-vault"\n', encoding="utf-8"
    )
    monkeypatch.chdir(child)

    assert ORIGINAL_GET_LOCAL_CONFIG_VAULT() == "toml-vault"

    (project / ".pkm").write_text('vault = "legacy-top-level"\n', encoding="utf-8")
    assert ORIGINAL_GET_LOCAL_CONFIG_VAULT() == "legacy-top-level"

    (project / ".pkm").write_text('vault="plain-vault"\n', encoding="utf-8")
    assert ORIGINAL_GET_LOCAL_CONFIG_VAULT() == "plain-vault"

    (project / ".pkm").write_text(
        "not toml\nvault = 'fallback-vault'\n", encoding="utf-8"
    )
    assert ORIGINAL_GET_LOCAL_CONFIG_VAULT() == "fallback-vault"


def test_local_config_resolver_ignores_unreadable_or_unparseable_files(
    monkeypatch, tmp_path
) -> None:
    """A bad .pkm directory/file is ignored instead of breaking vault resolution."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".pkm").mkdir()
    monkeypatch.chdir(project)

    assert ORIGINAL_GET_LOCAL_CONFIG_VAULT() is None


def test_parent_vault_resolves_parent_only_and_plain_text_fallback(
    monkeypatch, tmp_path
) -> None:
    """Parent vault lookup ignores current dir, then resolves parent .pkm through discovery."""
    vaults_root = tmp_path / "vaults"
    known = _make_vault(vaults_root, "known")
    project = tmp_path / "project"
    child = project / "child"
    child.mkdir(parents=True)
    (child / ".pkm").write_text('vault = "ignored-current"\n', encoding="utf-8")
    (project / ".pkm").write_text("vault=known\n", encoding="utf-8")
    monkeypatch.setattr(config, "get_vaults_root", lambda: vaults_root)

    result = config.get_parent_vault(child)

    assert result == known

    (project / ".pkm").write_text("vault=missing\n", encoding="utf-8")
    assert config.get_parent_vault(child) is None


def test_get_vault_context_local_config_precedes_env_and_global(
    monkeypatch, tmp_path
) -> None:
    """Vault context precedence uses local config before env/global config."""
    vaults_root = tmp_path / "vaults"
    local = _make_vault(vaults_root, "local")
    _make_vault(vaults_root, "env")
    _make_vault(vaults_root, "global")
    project = tmp_path / "project"
    project.mkdir()
    (project / ".pkm").write_text('[defaults]\nvault = "local"\n', encoding="utf-8")
    monkeypatch.chdir(project)
    monkeypatch.setattr(
        config, "get_local_config_vault", ORIGINAL_GET_LOCAL_CONFIG_VAULT
    )
    monkeypatch.setattr(config, "get_vaults_root", lambda: vaults_root)
    monkeypatch.setenv("PKM_DEFAULT_VAULT", "env")
    monkeypatch.setattr(
        config, "load_config", lambda: {"defaults": {"vault": "global"}}
    )

    vault, source = config.get_vault_context()

    assert vault == local
    assert source == "Local Config"


def test_get_vault_context_unknown_explicit_vault_reports_available(
    monkeypatch, tmp_path
) -> None:
    """Explicit unknown vaults fail with an actionable available-vault list."""
    vaults_root = tmp_path / "vaults"
    _make_vault(vaults_root, "known")
    monkeypatch.setattr(config, "get_vaults_root", lambda: vaults_root)

    with pytest.raises(click.ClickException, match="Unknown vault: missing"):
        config.get_vault_context("missing")


def test_web_config_reads_paths_and_falls_back_on_invalid_port(
    monkeypatch, tmp_path
) -> None:
    """Web config parses strings, expands user paths, and validates port."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(
        config,
        "load_config",
        lambda: {
            "web": {
                "port": "8123",
                "bind": "127.0.0.1",
                "token_path": "~/token",
                "password_path": "~/password",
                "session_reset_path": "~/reset",
            }
        },
    )

    web = config.get_web_config()

    assert web.port == 8123
    assert web.bind == "127.0.0.1"
    assert web.token_path == home / "token"
    assert web.password_path == home / "password"
    assert web.session_reset_path == home / "reset"

    monkeypatch.setattr(
        config,
        "load_config",
        lambda: {"web": {"port": "not-an-int"}},
    )
    assert config.get_web_config().port == 7420
