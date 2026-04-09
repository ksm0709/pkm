"""Tests for pkm config commands and config file infrastructure."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import load_config, save_config, get_vault, VaultConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_config_path(monkeypatch, tmp_path: Path) -> Path:
    config_path = tmp_path / ".config" / "pkm" / "config"
    monkeypatch.setattr("pkm.config.CONFIG_PATH", config_path)
    monkeypatch.setattr("pkm.commands.config.load_config", lambda: _load(config_path))
    monkeypatch.setattr(
        "pkm.commands.config.save_config", lambda d: _save(config_path, d)
    )
    return config_path


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    import tomllib

    with open(path, "rb") as f:
        return tomllib.load(f)


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for section, values in data.items():
        lines.append(f"[{section}]")
        for k, v in values.items():
            lines.append(f'{k} = "{v}"')
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _make_vault(tmp_path: Path, name: str) -> VaultConfig:
    p = tmp_path / name
    (p / "notes").mkdir(parents=True)
    return VaultConfig(name=name, path=p)


# ---------------------------------------------------------------------------
# load_config / save_config unit tests
# ---------------------------------------------------------------------------


def test_load_config_missing_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr("pkm.config.CONFIG_PATH", tmp_path / "nonexistent")
    assert load_config() == {}


def test_save_and_load_roundtrip(monkeypatch, tmp_path):
    config_path = tmp_path / "config"
    monkeypatch.setattr("pkm.config.CONFIG_PATH", config_path)
    save_config({"defaults": {"vault": "bear"}})
    assert load_config() == {"defaults": {"vault": "bear"}}


def test_save_creates_parent_dirs(monkeypatch, tmp_path):
    config_path = tmp_path / "nested" / "dir" / "config"
    monkeypatch.setattr("pkm.config.CONFIG_PATH", config_path)
    save_config({"defaults": {"vault": "bear"}})
    assert config_path.exists()


# ---------------------------------------------------------------------------
# get_vault() priority tests
# ---------------------------------------------------------------------------


def test_get_vault_uses_config_when_no_env(monkeypatch, tmp_path):
    vault = _make_vault(tmp_path, "mybear")
    monkeypatch.setattr(
        "pkm.config.discover_vaults", lambda root=None: {"mybear": vault}
    )
    monkeypatch.delenv("PKM_DEFAULT_VAULT", raising=False)
    monkeypatch.setattr(
        "pkm.config.load_config", lambda: {"defaults": {"vault": "mybear"}}
    )
    result = get_vault()
    assert result.name == "mybear"


def test_get_vault_env_overrides_config(monkeypatch, tmp_path):
    v1 = _make_vault(tmp_path, "from-env")
    v2 = _make_vault(tmp_path, "from-config")
    monkeypatch.setattr(
        "pkm.config.discover_vaults",
        lambda root=None: {"from-env": v1, "from-config": v2},
    )
    monkeypatch.setenv("PKM_DEFAULT_VAULT", "from-env")
    monkeypatch.setattr(
        "pkm.config.load_config", lambda: {"defaults": {"vault": "from-config"}}
    )
    result = get_vault()
    assert result.name == "from-env"


def test_get_vault_explicit_overrides_env(monkeypatch, tmp_path):
    v1 = _make_vault(tmp_path, "explicit")
    v2 = _make_vault(tmp_path, "from-env")
    monkeypatch.setattr(
        "pkm.config.discover_vaults", lambda root=None: {"explicit": v1, "from-env": v2}
    )
    monkeypatch.setenv("PKM_DEFAULT_VAULT", "from-env")
    result = get_vault("explicit")
    assert result.name == "explicit"


# ---------------------------------------------------------------------------
# pkm config set
# ---------------------------------------------------------------------------


def test_config_set_saves_to_file(monkeypatch, tmp_path):
    config_path = _patch_config_path(monkeypatch, tmp_path)
    vault = _make_vault(tmp_path, "bear")
    monkeypatch.setattr(
        "pkm.commands.config.discover_vaults", lambda root=None: {"bear": vault}
    )

    runner = CliRunner()
    result = runner.invoke(main, ["config", "set", "default-vault", "bear"])
    assert result.exit_code == 0, result.output
    assert "bear" in result.output

    saved = _load(config_path)
    assert saved["defaults"]["vault"] == "bear"


def test_config_set_warns_on_unknown_vault(monkeypatch, tmp_path):
    _patch_config_path(monkeypatch, tmp_path)
    monkeypatch.setattr("pkm.commands.config.discover_vaults", lambda root=None: {})

    runner = CliRunner()
    result = runner.invoke(main, ["config", "set", "default-vault", "ghost"])
    assert result.exit_code == 0
    assert "Warning" in result.output or "not found" in result.output


def test_config_set_invalid_key(monkeypatch, tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["config", "set", "bad-key", "value"])
    assert result.exit_code != 0
    assert "Unknown key" in result.output


# ---------------------------------------------------------------------------
# pkm config get
# ---------------------------------------------------------------------------


def test_config_get_returns_value(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pkm.commands.config.load_config", lambda: {"defaults": {"vault": "taeho"}}
    )

    runner = CliRunner()
    result = runner.invoke(main, ["config", "get", "default-vault"])
    assert result.exit_code == 0
    assert "taeho" in result.output


def test_config_get_not_set(monkeypatch):
    monkeypatch.setattr("pkm.commands.config.load_config", lambda: {})

    runner = CliRunner()
    result = runner.invoke(main, ["config", "get", "default-vault"])
    assert result.exit_code == 0
    assert "not set" in result.output


def test_config_get_invalid_key():
    runner = CliRunner()
    result = runner.invoke(main, ["config", "get", "bad-key"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# pkm config list
# ---------------------------------------------------------------------------


def test_config_list_shows_settings(monkeypatch):
    monkeypatch.setattr(
        "pkm.commands.config.load_config", lambda: {"defaults": {"vault": "bear"}}
    )

    runner = CliRunner()
    result = runner.invoke(main, ["config", "list"])
    assert result.exit_code == 0
    assert "default-vault" in result.output
    assert "bear" in result.output


def test_config_list_empty(monkeypatch):
    monkeypatch.setattr("pkm.commands.config.load_config", lambda: {})

    runner = CliRunner()
    result = runner.invoke(main, ["config", "list"])
    assert result.exit_code == 0
    assert "No configuration" in result.output


# ---------------------------------------------------------------------------
# vault-free: pkm config works without any vault present
# ---------------------------------------------------------------------------


def test_config_works_without_vault(monkeypatch):
    monkeypatch.setattr("pkm.config.discover_vaults", lambda root=None: {})
    monkeypatch.setattr("pkm.commands.config.load_config", lambda: {})

    runner = CliRunner()
    result = runner.invoke(main, ["config", "list"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# editor config key
# ---------------------------------------------------------------------------


def test_config_set_editor_saves(monkeypatch, tmp_path):
    config_path = _patch_config_path(monkeypatch, tmp_path)

    runner = CliRunner()
    result = runner.invoke(main, ["config", "set", "editor", "vim"])
    assert result.exit_code == 0, result.output
    assert "vim" in result.output

    saved = _load(config_path)
    assert saved["defaults"]["editor"] == "vim"


def test_config_set_editor_with_args(monkeypatch, tmp_path):
    config_path = _patch_config_path(monkeypatch, tmp_path)

    runner = CliRunner()
    result = runner.invoke(main, ["config", "set", "editor", "code --wait"])
    assert result.exit_code == 0, result.output

    saved = _load(config_path)
    assert saved["defaults"]["editor"] == "code --wait"


def test_config_get_editor(monkeypatch):
    monkeypatch.setattr(
        "pkm.commands.config.load_config",
        lambda: {"defaults": {"editor": "code --wait"}},
    )

    runner = CliRunner()
    result = runner.invoke(main, ["config", "get", "editor"])
    assert result.exit_code == 0
    assert "code --wait" in result.output


def test_config_list_includes_editor(monkeypatch):
    monkeypatch.setattr(
        "pkm.commands.config.load_config",
        lambda: {"defaults": {"vault": "bear", "editor": "vim"}},
    )

    runner = CliRunner()
    result = runner.invoke(main, ["config", "list"])
    assert result.exit_code == 0
    assert "editor" in result.output
    assert "vim" in result.output
