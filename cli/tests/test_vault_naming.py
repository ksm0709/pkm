"""Tests for git vault naming and migration in pkm.config."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


import pytest

from pkm.config import (
    VaultSuggestion,
    discover_vaults,
    ensure_vault_exists,
    get_git_vault_name,
    suggest_vault_name,
)


@pytest.mark.parametrize(
    "stdout, expected",
    [
        ("https://github.com/taeho/pkm.git\n", "@taeho--pkm"),
        ("git@github.com:taeho/pkm.git\n", "@taeho--pkm"),
    ],
)
def test_parse_remote(tmp_path, monkeypatch, stdout, expected):
    """get_git_vault_name parses remote URL into @owner--repo format."""
    monkeypatch.setattr("pkm.config._find_git_root", lambda cwd=None: tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = stdout

    with patch("subprocess.run", return_value=mock_result):
        name = get_git_vault_name()

    assert name == expected


def test_parse_no_remote(tmp_path, monkeypatch):
    """get_git_vault_name falls back to @{basename} when git remote fails."""
    monkeypatch.setattr("pkm.config._find_git_root", lambda cwd=None: tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""

    with patch("subprocess.run", return_value=mock_result):
        name = get_git_vault_name()

    assert name == f"@{tmp_path.name}"


def test_vault_migration_renames_dir(tmp_path, monkeypatch):
    """ensure_vault_exists renames old vault directory to new name."""
    monkeypatch.setattr("pkm.config.get_vaults_root", lambda: tmp_path)
    monkeypatch.setattr("pkm.config.load_config", lambda: {})
    monkeypatch.setattr("pkm.config.save_config", lambda d: None)

    old_vault = tmp_path / "pkm"
    old_vault.mkdir()
    (old_vault / "notes").mkdir()

    ensure_vault_exists("@taeho--pkm", old_name="pkm")

    assert (tmp_path / "@taeho--pkm").exists()
    assert not old_vault.exists()


def test_vault_migration_updates_config(tmp_path, monkeypatch):
    """ensure_vault_exists updates config vault reference after migration."""
    monkeypatch.setattr("pkm.config.get_vaults_root", lambda: tmp_path)

    saved = {}

    def fake_load_config():
        return {"defaults": {"vault": "pkm"}}

    def fake_save_config(data):
        saved.update(data)

    monkeypatch.setattr("pkm.config.load_config", fake_load_config)
    monkeypatch.setattr("pkm.config.save_config", fake_save_config)

    old_vault = tmp_path / "pkm"
    old_vault.mkdir()
    (old_vault / "notes").mkdir()

    ensure_vault_exists("@taeho--pkm", old_name="pkm")

    assert saved.get("defaults", {}).get("vault") == "@taeho--pkm"


def test_discover_vaults_includes_at_prefix(tmp_path, monkeypatch):
    """discover_vaults finds @-prefixed vault directories."""
    monkeypatch.setattr("pkm.config.get_vaults_root", lambda: tmp_path)

    at_vault = tmp_path / "@taeho--pkm"
    at_vault.mkdir()
    (at_vault / "notes").mkdir()

    vaults = discover_vaults(root=tmp_path)

    assert "@taeho--pkm" in vaults
    assert vaults["@taeho--pkm"].path == at_vault


def test_suggest_vault_name_returns_vault_suggestion(tmp_path, monkeypatch):
    """suggest_vault_name returns a VaultSuggestion dataclass."""
    monkeypatch.setattr("pkm.config._find_git_root", lambda cwd=None: None)
    monkeypatch.setattr("pkm.config.Path.home", lambda: tmp_path.parent)

    result = suggest_vault_name(cwd=tmp_path)

    assert isinstance(result, VaultSuggestion)
    assert isinstance(result.name, str)
    assert result.git_root is None
    assert result.is_subdir is False


def test_suggest_vault_name_git_subdir(tmp_path, monkeypatch):
    """suggest_vault_name returns is_subdir=True and @owner--repo--subdir name for git subdirs."""
    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    subdir = repo_root / "services" / "auth"
    subdir.mkdir(parents=True)

    monkeypatch.setattr("pkm.config._find_git_root", lambda cwd=None: repo_root)
    # Override the autouse fixture which patches get_git_vault_name to return None
    monkeypatch.setattr(
        "pkm.config.get_git_vault_name",
        lambda cwd=None: (
            "@taeho--myrepo--services--auth" if cwd == subdir else "@taeho--myrepo"
        ),
    )

    result = suggest_vault_name(cwd=subdir)

    assert result.is_subdir is True
    assert result.git_root == repo_root
    assert result.name == "@taeho--myrepo--services--auth"


def test_suggest_vault_name_non_git(tmp_path, monkeypatch):
    """suggest_vault_name returns home-relative path name for non-git dirs."""
    import getpass

    monkeypatch.setattr("pkm.config._find_git_root", lambda cwd=None: None)
    monkeypatch.setattr("pkm.config.Path.home", lambda: tmp_path)

    project_dir = tmp_path / "projects" / "myapp"
    project_dir.mkdir(parents=True)

    result = suggest_vault_name(cwd=project_dir)

    assert result.git_root is None
    assert result.is_subdir is False
    username = getpass.getuser()
    assert result.name == f"{username}--projects--myapp"


def test_suggest_vault_name_outside_home(tmp_path, monkeypatch):
    """suggest_vault_name falls back to basename when cwd is outside $HOME."""
    monkeypatch.setattr("pkm.config._find_git_root", lambda cwd=None: None)
    # Make Path.home() return something the cwd is NOT under
    monkeypatch.setattr("pkm.config.Path.home", lambda: tmp_path / "home")

    outside_dir = tmp_path / "opt" / "myapp"
    outside_dir.mkdir(parents=True)

    result = suggest_vault_name(cwd=outside_dir)

    assert result.git_root is None
    assert result.name == "myapp"  # basename fallback, no crash


def test_get_vault_context_does_not_auto_create_git_vault(tmp_path, monkeypatch):
    """get_vault_context must NOT create vault dirs for git project fallback.

    Vault directories must only be created via explicit `pkm vault setup`.
    If the git-derived vault doesn't exist yet, the fallback is skipped silently.
    """
    import pytest
    import click
    from pkm.config import get_vault_context

    vaults_root = tmp_path / "vaults"
    vaults_root.mkdir()

    monkeypatch.setattr("pkm.config.get_vaults_root", lambda: vaults_root)
    monkeypatch.setattr("pkm.config.get_local_config_vault", lambda: None)
    monkeypatch.delenv("PKM_DEFAULT_VAULT", raising=False)
    monkeypatch.setattr("pkm.config.load_config", lambda: {})
    monkeypatch.setattr(
        "pkm.config.get_git_vault_name", lambda cwd=None: "@taeho--myrepo"
    )
    monkeypatch.setattr("pkm.config._get_git_project_name_legacy", lambda: None)

    with pytest.raises(click.ClickException):
        get_vault_context()

    # The vault directory must NOT have been created automatically
    assert not (vaults_root / "@taeho--myrepo").exists()


def test_get_vault_context_uses_existing_git_vault(tmp_path, monkeypatch):
    """get_vault_context uses git-derived vault when it already exists on disk."""
    from pkm.config import get_vault_context

    vaults_root = tmp_path / "vaults"
    vault_path = vaults_root / "@taeho--myrepo"
    (vault_path / "daily").mkdir(parents=True)
    (vault_path / "notes").mkdir()

    monkeypatch.setattr("pkm.config.get_vaults_root", lambda: vaults_root)
    monkeypatch.setattr("pkm.config.get_local_config_vault", lambda: None)
    monkeypatch.delenv("PKM_DEFAULT_VAULT", raising=False)
    monkeypatch.setattr("pkm.config.load_config", lambda: {})
    monkeypatch.setattr(
        "pkm.config.get_git_vault_name", lambda cwd=None: "@taeho--myrepo"
    )
    monkeypatch.setattr("pkm.config._get_git_project_name_legacy", lambda: None)

    vc, source = get_vault_context()

    assert vc.name == "@taeho--myrepo"
    assert source == "Git Project"


def test_get_vault_context_git_vault_missing_falls_back_to_global_config(
    tmp_path, monkeypatch
):
    """git vault name found but directory missing → falls back to Global Config vault.

    Regression: the original elif chain consumed the git-project branch without
    setting `name`, so Global Config and First Discovered fallbacks never ran.
    """
    from pkm.config import get_vault_context

    vaults_root = tmp_path / "vaults"
    fallback_vault = vaults_root / "default"
    (fallback_vault / "daily").mkdir(parents=True)
    (fallback_vault / "notes").mkdir()

    monkeypatch.setattr("pkm.config.get_vaults_root", lambda: vaults_root)
    monkeypatch.setattr("pkm.config.get_local_config_vault", lambda: None)
    monkeypatch.delenv("PKM_DEFAULT_VAULT", raising=False)
    monkeypatch.setattr(
        "pkm.config.load_config", lambda: {"defaults": {"vault": "default"}}
    )
    monkeypatch.setattr(
        "pkm.config.get_git_vault_name", lambda cwd=None: "@taeho--myrepo"
    )
    monkeypatch.setattr("pkm.config._get_git_project_name_legacy", lambda: None)

    # @taeho--myrepo dir does NOT exist → should fall back to Global Config
    assert not (vaults_root / "@taeho--myrepo").exists()

    vc, source = get_vault_context()

    assert vc.name == "default"
    assert source == "Global Config"


def test_get_vault_context_git_vault_missing_falls_back_to_first_discovered(
    tmp_path, monkeypatch
):
    """git vault name found but directory missing → falls back to First Discovered vault.

    Regression: same elif-chain bug; Global Config also absent means First Discovered
    must still be reachable.
    """
    from pkm.config import get_vault_context

    vaults_root = tmp_path / "vaults"
    discovered_vault = vaults_root / "personal"
    (discovered_vault / "daily").mkdir(parents=True)
    (discovered_vault / "notes").mkdir()

    monkeypatch.setattr("pkm.config.get_vaults_root", lambda: vaults_root)
    monkeypatch.setattr("pkm.config.get_local_config_vault", lambda: None)
    monkeypatch.delenv("PKM_DEFAULT_VAULT", raising=False)
    monkeypatch.setattr("pkm.config.load_config", lambda: {})
    monkeypatch.setattr(
        "pkm.config.get_git_vault_name", lambda cwd=None: "@taeho--myrepo"
    )
    monkeypatch.setattr("pkm.config._get_git_project_name_legacy", lambda: None)

    assert not (vaults_root / "@taeho--myrepo").exists()

    vc, source = get_vault_context()

    assert vc.name == "personal"
    assert source == "First Discovered"


def test_get_vault_context_migrates_legacy_vault_without_creating(
    tmp_path, monkeypatch
):
    """get_vault_context migrates old vault name to new name without creating fresh dirs."""
    from pkm.config import get_vault_context

    vaults_root = tmp_path / "vaults"
    old_vault = vaults_root / "myrepo"
    (old_vault / "daily").mkdir(parents=True)
    (old_vault / "notes").mkdir()

    monkeypatch.setattr("pkm.config.get_vaults_root", lambda: vaults_root)
    monkeypatch.setattr("pkm.config.get_local_config_vault", lambda: None)
    monkeypatch.delenv("PKM_DEFAULT_VAULT", raising=False)
    monkeypatch.setattr("pkm.config.load_config", lambda: {})
    monkeypatch.setattr("pkm.config.save_config", lambda d: None)
    monkeypatch.setattr(
        "pkm.config.get_git_vault_name", lambda cwd=None: "@taeho--myrepo"
    )
    monkeypatch.setattr("pkm.config._get_git_project_name_legacy", lambda: "myrepo")

    vc, source = get_vault_context()

    assert vc.name == "@taeho--myrepo"
    assert source == "Git Project"
    assert (vaults_root / "@taeho--myrepo").exists()
    assert not old_vault.exists()
