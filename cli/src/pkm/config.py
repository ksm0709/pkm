"""Vault discovery and configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import click


DEFAULT_VAULTS_ROOT = Path.home() / "vaults"
CONFIG_PATH = Path.home() / ".config" / "pkm" / "config"


def load_config() -> dict:
    """Load ~/.config/pkm/config as a dict. Returns {} if file missing."""
    if not CONFIG_PATH.exists():
        return {}
    import tomllib
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def save_config(data: dict) -> None:
    """Save data to ~/.config/pkm/config in TOML format."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Serialize manually — structure is simple ([defaults] section only)
    lines = []
    for section, values in data.items():
        lines.append(f"[{section}]")
        for k, v in values.items():
            lines.append(f'{k} = "{v}"')
        lines.append("")
    CONFIG_PATH.write_text("\n".join(lines), encoding="utf-8")


@dataclass(frozen=True)
class VaultConfig:
    name: str
    path: Path

    @property
    def daily_dir(self) -> Path:
        return self.path / "daily"

    @property
    def notes_dir(self) -> Path:
        return self.path / "notes"

    @property
    def tasks_dir(self) -> Path:
        return self.path / "tasks"

    @property
    def data_dir(self) -> Path:
        return self.path / "data"

    @property
    def pkm_dir(self) -> Path:
        return self.path / ".pkm"

    @property
    def artifacts_dir(self) -> Path:
        return self.pkm_dir / "artifacts"


def get_vaults_root() -> Path:
    """Resolve vaults root from PKM_VAULTS_ROOT env var or default."""
    return Path(os.environ.get("PKM_VAULTS_ROOT", str(DEFAULT_VAULTS_ROOT)))


def discover_vaults(root: Path | None = None) -> dict[str, VaultConfig]:
    """Auto-discover vaults under root directory.

    A directory is considered a vault if it contains a `daily/` or `notes/` subdirectory.
    """
    root = root or get_vaults_root()
    vaults: dict[str, VaultConfig] = {}
    if not root.is_dir():
        return vaults
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if (child / "daily").is_dir() or (child / "notes").is_dir():
            vaults[child.name] = VaultConfig(name=child.name, path=child)
    return vaults


def get_vault(name: str | None = None) -> VaultConfig:
    """Get a vault by name. If name is None, use PKM_DEFAULT_VAULT env or first discovered."""
    vaults = discover_vaults()
    if not vaults:
        raise click.ClickException(
            f"No vaults found under {get_vaults_root()}. "
            "A vault needs a daily/ or notes/ subdirectory."
        )
    if name is None:
        name = os.environ.get("PKM_DEFAULT_VAULT")
    if name is None:
        name = load_config().get("defaults", {}).get("vault")
    if name is None:
        name = next(iter(vaults))
    if name not in vaults:
        raise click.ClickException(
            f"Unknown vault: {name}. Available: {', '.join(vaults)}"
        )
    return vaults[name]
