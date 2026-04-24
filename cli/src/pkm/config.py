import getpass
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

DEFAULT_VAULTS_ROOT = Path.home() / "vaults"
CONFIG_PATH = Path.home() / ".config" / "pkm" / "config"


def load_config() -> dict[str, Any]:
    """Load ~/.config/pkm/config as a dict. Returns {} if file missing."""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def save_config(data: dict[str, Any]) -> None:
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


@dataclass
class VaultSuggestion:
    name: str
    git_root: Path | None
    is_subdir: bool


@dataclass(frozen=True)
class VaultConfig:
    name: str
    path: Path
    task_statuses: dict = field(
        default_factory=lambda: {
            "todo": ["TODO", "[ ]"],
            "wip": ["WIP", "[>]"],
            "done": ["DONE", "[x]"],
            "cancel": ["CANCEL", "[-]"],
        }
    )
    task_assignee_patterns: list = field(default_factory=list)

    @property
    def daily_dir(self) -> Path:
        return self.path / "daily"

    @property
    def notes_dir(self) -> Path:
        return self.path / "notes"

    @property
    def tags_dir(self) -> Path:
        return self.path / "tags"

    @property
    def data_dir(self) -> Path:
        return self.path / "data"

    @property
    def pkm_dir(self) -> Path:
        return self.path / ".pkm"

    @property
    def artifacts_dir(self) -> Path:
        return self.pkm_dir / "artifacts"

    @property
    def graph_path(self) -> Path:
        return self.pkm_dir / "graph.json"

    @property
    def graph_enriched_path(self) -> Path:
        return self.pkm_dir / "graph_enriched.json"


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


def get_local_config_vault() -> str | None:
    """Check for .pkm file in cwd or parents and extract vault name."""
    current = Path.cwd()
    for path in [current, *current.parents]:
        pkm_file = path / ".pkm"
        if pkm_file.exists():
            try:
                with open(pkm_file, "rb") as f:
                    data = tomllib.load(f)
                    if "defaults" in data and "vault" in data["defaults"]:
                        return data["defaults"]["vault"]
                    elif "vault" in data:
                        return data["vault"]
            except Exception:
                pass

            try:
                content = pkm_file.read_text(encoding="utf-8").strip()
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("vault=") or line.startswith("vault ="):
                        return line.split("=", 1)[1].strip().strip("\"'")
            except Exception:
                pass
    return None


def get_parent_vault(current_dir: Path | None = None) -> VaultConfig | None:
    """Check for .pkm file in parent directories and return the VaultConfig."""
    current = current_dir or Path.cwd()
    for path in current.parents:
        pkm_file = path / ".pkm"
        name = None
        if pkm_file.exists():
            try:
                with open(pkm_file, "rb") as f:
                    data = tomllib.load(f)
                    if "defaults" in data and "vault" in data["defaults"]:
                        name = data["defaults"]["vault"]
                    elif "vault" in data:
                        name = data["vault"]
            except Exception:
                pass

            if name is None:
                try:
                    content = pkm_file.read_text(encoding="utf-8").strip()
                    for line in content.splitlines():
                        line = line.strip()
                        if line.startswith("vault=") or line.startswith("vault ="):
                            name = line.split("=", 1)[1].strip().strip("\"'")
                except Exception:
                    pass

        if name:
            vaults = discover_vaults()
            if name in vaults:
                return vaults[name]
    return None


def _find_git_root(cwd: Path | None = None) -> Path | None:
    """Find the git root directory from cwd, or None."""
    current = cwd or Path.cwd()
    for path in [current, *current.parents]:
        if (path / ".git").exists():
            return path
    return None


def get_git_vault_name(cwd: Path | None = None) -> str | None:
    """Return @owner--repo vault name from git remote, or @basename fallback.

    If cwd is inside a git repo but not at the root, appends --subdir suffix.
    """
    import re
    import subprocess

    actual_cwd = cwd or Path.cwd()
    git_root = _find_git_root(cwd=actual_cwd)
    if git_root is None:
        return None

    base_name: str
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(git_root),
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            m = re.match(
                r"(?:https?://[^/]+/|git@[^:]+:)([^/]+)/([^/.]+)",
                url,
            )
            if m:
                owner, repo = m.group(1), m.group(2)
                base_name = f"@{owner}--{repo}"
            else:
                base_name = f"@{git_root.name}"
        else:
            base_name = f"@{git_root.name}"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        base_name = f"@{git_root.name}"

    # Append subdir suffix when cwd is not the git root
    if actual_cwd.resolve() != git_root.resolve():
        try:
            rel = actual_cwd.resolve().relative_to(git_root.resolve())
            subdir = "--".join(rel.parts)
            return f"{base_name}--{subdir}"
        except ValueError:
            pass

    return base_name


def suggest_vault_name(cwd: Path | None = None) -> VaultSuggestion:
    """Suggest a vault name based on the current directory context.

    Returns a VaultSuggestion with name, git_root, and is_subdir fields.
    Uses getpass.getuser() (not os.getlogin()) for safety in headless environments.
    """
    actual_cwd = cwd or Path.cwd()
    git_root = _find_git_root(cwd=actual_cwd)

    if git_root is not None:
        name = get_git_vault_name(cwd=actual_cwd) or f"@{git_root.name}"
        is_subdir = actual_cwd.resolve() != git_root.resolve()
        return VaultSuggestion(name=name, git_root=git_root, is_subdir=is_subdir)

    # Non-git: derive from home-relative path components
    username = getpass.getuser()
    try:
        rel = actual_cwd.relative_to(Path.home())
        name = "--".join([username] + list(rel.parts))
    except ValueError:
        # Outside $HOME: fallback to directory basename only
        name = actual_cwd.name

    return VaultSuggestion(name=name, git_root=None, is_subdir=False)


def _get_git_project_name_legacy() -> str | None:
    """Return plain basename of git root (for migration detection only)."""
    git_root = _find_git_root()
    return git_root.name if git_root else None


def _migrate_git_vault(vault_name: str) -> None:
    """Migrate legacy git vault name if needed."""
    old_name = _get_git_project_name_legacy()
    root = get_vaults_root()
    vault_path = root / vault_name
    # Migrate from legacy name if needed (rename only, never auto-create)
    if not vault_path.exists() and old_name:
        old_path = root / old_name
        if old_path.exists():
            import shutil as _shutil

            _shutil.move(str(old_path), str(vault_path))
            _update_config_vault_reference(old_name, vault_name)


def ensure_vault_exists(name: str, old_name: str | None = None) -> None:
    """Create vault directory structure if it doesn't exist.

    If old_name is provided and its directory exists, migrate it to the new name.
    """
    root = get_vaults_root()
    vault_path = root / name
    if vault_path.exists():
        return

    # Migrate from old vault name if it exists
    if old_name:
        old_path = root / old_name
        if old_path.exists():
            import shutil

            shutil.move(str(old_path), str(vault_path))
            _update_config_vault_reference(old_name, name)
            return

    (vault_path / "daily").mkdir(parents=True, exist_ok=True)
    (vault_path / "notes").mkdir(parents=True, exist_ok=True)
    (vault_path / "tags").mkdir(parents=True, exist_ok=True)


def _update_config_vault_reference(old_name: str, new_name: str) -> None:
    """Update vault name references in global config after migration."""
    data = load_config()
    defaults = data.get("defaults", {})
    if defaults.get("vault") == old_name:
        data.setdefault("defaults", {})["vault"] = new_name
        save_config(data)


def get_vault_context(name: str | None = None) -> tuple[VaultConfig, str]:
    """Get a vault by name following precedence rules, returning the vault and the resolution source."""
    source = ""
    if name is not None:
        source = "CLI Arg"
    elif (name := get_local_config_vault()) is not None:
        source = "Local Config"
    elif (name := os.environ.get("PKM_DEFAULT_VAULT")) is not None:
        source = "Env Var"
    elif vault_name := get_git_vault_name():
        _migrate_git_vault(vault_name)
        if (get_vaults_root() / vault_name).is_dir():
            name = vault_name
            source = "Git Project"
    elif (name := load_config().get("defaults", {}).get("vault")) is not None:
        source = "Global Config"
    else:
        vaults = discover_vaults()
        if vaults:
            name = next(iter(vaults))
            source = "First Discovered"
        else:
            raise click.ClickException(
                f"No vaults found under {get_vaults_root()}. "
                "A vault needs a daily/ or notes/ subdirectory."
            )

    vaults = discover_vaults()
    if name not in vaults:
        raise click.ClickException(
            f"Unknown vault: {name}. Available: {', '.join(vaults) if vaults else 'None'}"
        )

    return vaults[name], source


def get_vault(name: str | None = None) -> VaultConfig:
    """Get a vault by name following precedence rules."""
    return get_vault_context(name)[0]
