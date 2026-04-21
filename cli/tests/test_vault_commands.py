"""Tests for vault management commands: list, add, remove."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig


def _make_vaults(tmp_path: Path) -> dict[str, VaultConfig]:
    """Create two minimal vaults under tmp_path."""
    vaults = {}
    for name in ("alpha", "beta"):
        p = tmp_path / name
        (p / "daily").mkdir(parents=True)
        (p / "notes").mkdir()
        (p / "notes" / "note1.md").write_text("# note", encoding="utf-8")
        (p / "daily" / "2026-04-01.md").write_text("# daily", encoding="utf-8")
        vaults[name] = VaultConfig(name=name, path=p)
    return vaults


def _patch_vaults(monkeypatch, vaults: dict[str, VaultConfig]) -> None:
    monkeypatch.setattr("pkm.config.discover_vaults", lambda root=None: vaults)
    monkeypatch.setattr("pkm.commands.vault.discover_vaults", lambda root=None: vaults)


@pytest.fixture
def vaults(tmp_path: Path) -> dict[str, VaultConfig]:
    return _make_vaults(tmp_path)


@pytest.fixture
def patched_vaults(
    monkeypatch, vaults: dict[str, VaultConfig]
) -> dict[str, VaultConfig]:
    _patch_vaults(monkeypatch, vaults)
    return vaults


# ---------------------------------------------------------------------------
# vault edit
# ---------------------------------------------------------------------------


def test_vault_edit_opens_editor(patched_vaults, monkeypatch):
    mock_run = []

    monkeypatch.setattr(
        "pkm.commands.vault.subprocess.run", lambda args: mock_run.append(args)
    )
    monkeypatch.setattr(
        "pkm.commands.vault.load_config", lambda: {"editor": "code --wait"}
    )

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "edit", "alpha"])
    assert result.exit_code == 0, result.output
    assert len(mock_run) == 1
    assert mock_run[0] == ["code", "--wait", str(patched_vaults["alpha"].path)]


def test_vault_edit_active_vault(patched_vaults, monkeypatch):
    # Mock get_vault_context to return alpha as active
    monkeypatch.setattr(
        "pkm.config.get_vault_context", lambda: (patched_vaults["alpha"], "config")
    )

    mock_run = []

    monkeypatch.setattr(
        "pkm.commands.vault.subprocess.run", lambda args: mock_run.append(args)
    )
    monkeypatch.setattr("pkm.commands.vault.load_config", lambda: {"editor": "vim"})

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "edit"])
    assert result.exit_code == 0, result.output
    assert len(mock_run) == 1
    assert mock_run[0] == ["vim", str(patched_vaults["alpha"].path)]


def test_vault_list_shows_table(patched_vaults, monkeypatch):
    runner = CliRunner()
    result = runner.invoke(main, ["vault", "list"])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output
    assert "beta" in result.output


def test_vault_list_shows_counts(patched_vaults, monkeypatch):
    runner = CliRunner()
    result = runner.invoke(main, ["vault", "list"])
    assert result.exit_code == 0
    # Each vault has 1 note and 1 daily
    assert "1" in result.output


def test_vault_list_marks_default(patched_vaults, monkeypatch):
    import json as _json

    monkeypatch.setenv("PKM_DEFAULT_VAULT", "beta")

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "list"])
    assert result.exit_code == 0
    data = _json.loads(result.output)
    assert data["active"] == "beta"
    active_vaults = [v for v in data["vaults"] if v["active"]]
    assert len(active_vaults) >= 1


def test_vault_list_empty(monkeypatch):
    import json as _json

    monkeypatch.setattr("pkm.config.discover_vaults", lambda root=None: {})
    monkeypatch.setattr("pkm.commands.vault.discover_vaults", lambda root=None: {})

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "list"])
    assert result.exit_code == 0
    data = _json.loads(result.output)
    assert data["vaults"] == []


# ---------------------------------------------------------------------------
# vault add
# ---------------------------------------------------------------------------


def test_vault_add_creates_structure(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("pkm.commands.vault.get_vaults_root", lambda: tmp_path)

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "add", "mynewvault"])
    assert result.exit_code == 0, result.output

    vault_path = tmp_path / "mynewvault"
    assert (vault_path / "daily").is_dir()
    assert (vault_path / "notes").is_dir()
    assert (vault_path / "tasks").is_dir()
    assert (vault_path / "tasks" / "archive").is_dir()
    assert (vault_path / "data").is_dir()
    assert (vault_path / ".pkm").is_dir()
    assert (vault_path / ".pkm" / "artifacts").is_dir()
    assert (vault_path / "tasks" / "ongoing.md").is_file()


def test_vault_add_ongoing_md_content(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("pkm.commands.vault.get_vaults_root", lambda: tmp_path)

    runner = CliRunner()
    runner.invoke(main, ["vault", "add", "myvault"])

    ongoing = tmp_path / "myvault" / "tasks" / "ongoing.md"
    content = ongoing.read_text(encoding="utf-8")
    assert "myvault-ongoing-tasks" in content
    assert "In Progress" in content
    assert "🔴" in content


def test_vault_add_already_exists(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("pkm.commands.vault.get_vaults_root", lambda: tmp_path)
    (tmp_path / "existing").mkdir()

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "add", "existing"])
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_vault_add_invalid_name(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("pkm.commands.vault.get_vaults_root", lambda: tmp_path)

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "add", "bad/name"])
    assert result.exit_code != 0
    assert "Invalid vault name" in result.output


# ---------------------------------------------------------------------------
# vault remove
# ---------------------------------------------------------------------------


def test_vault_remove_moves_to_trash(patched_vaults, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("pkm.commands.vault.Path.home", lambda: tmp_path / "home")

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "remove", "--yes", "alpha"])
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "alpha").exists()


def test_vault_remove_shows_stats(patched_vaults, monkeypatch):
    runner = CliRunner()
    result = runner.invoke(main, ["vault", "remove", "--yes", "alpha"])
    assert result.exit_code == 0, result.output
    assert "note" in result.output or "1" in result.output


def test_vault_remove_shows_trash_path(patched_vaults, monkeypatch):
    runner = CliRunner()
    result = runner.invoke(main, ["vault", "remove", "--yes", "alpha"])
    assert result.exit_code == 0, result.output
    assert "trash" in result.output


def test_vault_remove_confirmation_prompt(patched_vaults, tmp_path: Path, monkeypatch):
    runner = CliRunner()
    result = runner.invoke(main, ["vault", "remove", "alpha"], input="n\n")
    assert result.exit_code != 0
    assert (tmp_path / "alpha").exists()


def test_vault_remove_not_found(patched_vaults, monkeypatch):
    runner = CliRunner()
    result = runner.invoke(main, ["vault", "remove", "--yes", "nonexistent"])
    assert result.exit_code != 0
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# vault open
# ---------------------------------------------------------------------------


def test_vault_open_sets_default(patched_vaults, monkeypatch):
    saved = {}

    def fake_save(data):
        saved.update(data)

    monkeypatch.setattr("pkm.commands.vault.load_config", lambda: {})
    monkeypatch.setattr("pkm.commands.vault.save_config", fake_save)

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "open", "beta"])
    assert result.exit_code == 0, result.output
    assert saved["defaults"]["vault"] == "beta"


def test_vault_open_shows_success(patched_vaults, monkeypatch):
    monkeypatch.setattr("pkm.commands.vault.load_config", lambda: {})
    monkeypatch.setattr("pkm.commands.vault.save_config", lambda d: None)

    runner = CliRunner()
    result = runner.invoke(main, ["vault", "open", "alpha"])
    assert result.exit_code == 0
    assert "alpha" in result.output


def test_vault_open_not_found(patched_vaults, monkeypatch):
    runner = CliRunner()
    result = runner.invoke(main, ["vault", "open", "nonexistent"])
    assert result.exit_code != 0
    assert "not found" in result.output or "nonexistent" in result.output


# ---------------------------------------------------------------------------
# vault setup
# ---------------------------------------------------------------------------


def test_vault_setup_creates_pkm_and_dirs(tmp_path: Path, monkeypatch):
    """Happy path: setup creates .pkm file and vault directories."""
    from pkm.config import VaultSuggestion

    cwd = tmp_path / "myproject"
    cwd.mkdir()
    vaults_root = tmp_path / "vaults"

    monkeypatch.setattr(
        "pkm.commands.vault.suggest_vault_name",
        lambda cwd=None: VaultSuggestion(
            name="@taeho--myproject", git_root=None, is_subdir=False
        ),
    )
    monkeypatch.setattr("pkm.commands.vault.get_vaults_root", lambda: vaults_root)

    runner = CliRunner()
    import os

    orig_cwd = os.getcwd()
    try:
        os.chdir(cwd)
        result = runner.invoke(
            main, ["vault", "setup"], input="\n", catch_exceptions=False
        )
    finally:
        os.chdir(orig_cwd)

    assert result.exit_code == 0, result.output
    assert (cwd / ".pkm").exists()
    pkm_content = (cwd / ".pkm").read_text()
    assert "@taeho--myproject" in pkm_content
    assert (vaults_root / "@taeho--myproject" / "daily").is_dir()
    assert (vaults_root / "@taeho--myproject" / "notes").is_dir()


def test_vault_setup_custom_name(tmp_path: Path, monkeypatch):
    """User overrides the suggested name."""
    from pkm.config import VaultSuggestion
    import os

    cwd = tmp_path / "myproject"
    cwd.mkdir()
    vaults_root = tmp_path / "vaults"

    monkeypatch.setattr(
        "pkm.commands.vault.suggest_vault_name",
        lambda cwd=None: VaultSuggestion(
            name="@taeho--myproject", git_root=None, is_subdir=False
        ),
    )
    monkeypatch.setattr("pkm.commands.vault.get_vaults_root", lambda: vaults_root)

    runner = CliRunner()
    orig_cwd = os.getcwd()
    try:
        os.chdir(cwd)
        result = runner.invoke(
            main, ["vault", "setup"], input="my-custom-vault\n", catch_exceptions=False
        )
    finally:
        os.chdir(orig_cwd)

    assert result.exit_code == 0, result.output
    pkm_content = (cwd / ".pkm").read_text()
    assert "my-custom-vault" in pkm_content
    assert (vaults_root / "my-custom-vault" / "daily").is_dir()


def test_vault_setup_already_exists(tmp_path: Path, monkeypatch):
    """Running setup when .pkm already exists shows error."""
    import os

    cwd = tmp_path / "myproject"
    cwd.mkdir()
    (cwd / ".pkm").write_text('vault = "existing"\n')

    runner = CliRunner()
    orig_cwd = os.getcwd()
    try:
        os.chdir(cwd)
        result = runner.invoke(main, ["vault", "setup"])
    finally:
        os.chdir(orig_cwd)

    assert result.exit_code != 0
    assert "already" in result.output.lower() or "pkm vault list" in result.output


def test_vault_setup_git_subdir_creates_root_pkm(tmp_path: Path, monkeypatch):
    """In a git subdir, repo root gets a .pkm file (if not present)."""
    from pkm.config import VaultSuggestion
    import os

    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    subdir = repo_root / "auth"
    subdir.mkdir()
    vaults_root = tmp_path / "vaults"

    monkeypatch.setattr(
        "pkm.commands.vault.suggest_vault_name",
        lambda cwd=None: (
            VaultSuggestion(
                name="@taeho--myrepo--auth", git_root=repo_root, is_subdir=True
            )
            if cwd is None or cwd == subdir
            else VaultSuggestion(
                name="@taeho--myrepo", git_root=repo_root, is_subdir=False
            )
        ),
    )
    monkeypatch.setattr("pkm.commands.vault.get_vaults_root", lambda: vaults_root)

    runner = CliRunner()
    orig_cwd = os.getcwd()
    try:
        os.chdir(subdir)
        result = runner.invoke(
            main, ["vault", "setup"], input="\n", catch_exceptions=False
        )
    finally:
        os.chdir(orig_cwd)

    assert result.exit_code == 0, result.output
    assert (repo_root / ".pkm").exists()
    root_content = (repo_root / ".pkm").read_text()
    assert "@taeho--myrepo" in root_content
    assert "Also created .pkm at repo root" in result.output


def test_vault_setup_git_subdir_no_overwrite_root(tmp_path: Path, monkeypatch):
    """Root .pkm is NOT overwritten if it already exists."""
    from pkm.config import VaultSuggestion
    import os

    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    subdir = repo_root / "auth"
    subdir.mkdir()
    existing_root_pkm = repo_root / ".pkm"
    existing_root_pkm.write_text('vault = "original"\n')
    vaults_root = tmp_path / "vaults"

    monkeypatch.setattr(
        "pkm.commands.vault.suggest_vault_name",
        lambda cwd=None: VaultSuggestion(
            name="@taeho--myrepo--auth", git_root=repo_root, is_subdir=True
        ),
    )
    monkeypatch.setattr("pkm.commands.vault.get_vaults_root", lambda: vaults_root)

    runner = CliRunner()
    orig_cwd = os.getcwd()
    try:
        os.chdir(subdir)
        result = runner.invoke(
            main, ["vault", "setup"], input="\n", catch_exceptions=False
        )
    finally:
        os.chdir(orig_cwd)

    assert result.exit_code == 0, result.output
    assert existing_root_pkm.read_text() == 'vault = "original"\n'


def test_vault_setup_non_git(tmp_path: Path, monkeypatch):
    """Non-git directory uses username--path naming."""
    from pkm.config import VaultSuggestion
    import os

    cwd = tmp_path / "projects" / "myapp"
    cwd.mkdir(parents=True)
    vaults_root = tmp_path / "vaults"

    monkeypatch.setattr(
        "pkm.commands.vault.suggest_vault_name",
        lambda cwd=None: VaultSuggestion(
            name="taeho--projects--myapp", git_root=None, is_subdir=False
        ),
    )
    monkeypatch.setattr("pkm.commands.vault.get_vaults_root", lambda: vaults_root)

    runner = CliRunner()
    orig_cwd = os.getcwd()
    try:
        os.chdir(cwd)
        result = runner.invoke(
            main, ["vault", "setup"], input="\n", catch_exceptions=False
        )
    finally:
        os.chdir(orig_cwd)

    assert result.exit_code == 0, result.output
    pkm_content = (cwd / ".pkm").read_text()
    assert "taeho--projects--myapp" in pkm_content


def test_vault_setup_gitignore_tip(tmp_path: Path, monkeypatch):
    """Success output includes the .gitignore tip."""
    from pkm.config import VaultSuggestion
    import os

    cwd = tmp_path / "myproject"
    cwd.mkdir()
    vaults_root = tmp_path / "vaults"

    monkeypatch.setattr(
        "pkm.commands.vault.suggest_vault_name",
        lambda cwd=None: VaultSuggestion(
            name="myproject", git_root=None, is_subdir=False
        ),
    )
    monkeypatch.setattr("pkm.commands.vault.get_vaults_root", lambda: vaults_root)

    runner = CliRunner()
    orig_cwd = os.getcwd()
    try:
        os.chdir(cwd)
        result = runner.invoke(
            main, ["vault", "setup"], input="\n", catch_exceptions=False
        )
    finally:
        os.chdir(orig_cwd)

    assert result.exit_code == 0, result.output
    assert ".gitignore" in result.output


def test_vault_unset_migrates_to_parent(tmp_path: Path, monkeypatch):

    runner = CliRunner()

    parent_storage = tmp_path / "parent_vault"
    parent_storage.mkdir()
    (parent_storage / "daily").mkdir()

    child_storage = tmp_path / "child_vault"
    child_storage.mkdir()
    (child_storage / "daily").mkdir()

    parent_project = tmp_path / "parent_project"
    parent_project.mkdir()
    (parent_project / ".pkm").write_text('vault = "parent_vault"')

    child_project = parent_project / "child_project"
    child_project.mkdir()
    (child_project / ".pkm").write_text('vault = "child_vault"')

    (child_storage / "daily" / "2026-04-11.md").write_text("child daily")
    (parent_storage / "daily" / "2026-04-11.md").write_text("parent daily")

    monkeypatch.setattr("pkm.config.get_vaults_root", lambda: tmp_path)
    monkeypatch.setattr("pkm.config.get_local_config_vault", lambda: "child_vault")
    monkeypatch.chdir(child_project)

    result = runner.invoke(main, ["vault", "unset"])
    assert result.exit_code == 0, result.output
    assert "Migrating vault child_vault to root vault parent_vault" in result.output

    # Check that .pkm is removed from child
    assert not (child_project / ".pkm").exists()


def test_vault_unset_merges_daily_notes(tmp_path: Path, monkeypatch):
    """When both vaults have the same daily note, entries are merged by time."""
    runner = CliRunner()

    parent_storage = tmp_path / "parent_vault"
    parent_storage.mkdir()
    (parent_storage / "daily").mkdir()
    (parent_storage / "notes").mkdir()
    (parent_storage / ".pkm").mkdir()

    child_storage = tmp_path / "child_vault"
    child_storage.mkdir()
    (child_storage / "daily").mkdir()
    (child_storage / "notes").mkdir()
    (child_storage / ".pkm").mkdir()

    parent_project = tmp_path / "parent_project"
    parent_project.mkdir()
    (parent_project / ".pkm").write_text('vault = "parent_vault"')

    child_project = parent_project / "child_project"
    child_project.mkdir()
    (child_project / ".pkm").write_text('vault = "child_vault"')

    # Parent has entries at 09:00
    (parent_storage / "daily" / "2026-04-16.md").write_text(
        "---\nid: 2026-04-16\ntags:\n  - daily-notes\n---\n"
        "- [09:00] parent entry alpha\n"
        "## TODO\n",
        encoding="utf-8",
    )
    # Child has entries at 08:00 and 10:00
    (child_storage / "daily" / "2026-04-16.md").write_text(
        "---\nid: 2026-04-16\ntags:\n  - daily-notes\n  - child-tag\n---\n"
        "- [08:00] child entry early\n"
        "- [10:00] child entry late\n"
        "## TODO\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("pkm.config.get_vaults_root", lambda: tmp_path)
    monkeypatch.setattr("pkm.config.get_local_config_vault", lambda: "child_vault")
    monkeypatch.chdir(child_project)

    result = runner.invoke(main, ["vault", "unset"])
    assert result.exit_code == 0, result.output

    # Verify merged daily note
    merged = (parent_storage / "daily" / "2026-04-16.md").read_text(encoding="utf-8")

    # No _migrated file should exist
    migrated_files = list((parent_storage / "daily").glob("*migrated*"))
    assert migrated_files == [], f"Should not create migrated files: {migrated_files}"

    # All 3 entries present, sorted by time
    assert "child entry early" in merged
    assert "parent entry alpha" in merged
    assert "child entry late" in merged
    lines = [ln.strip() for ln in merged.splitlines() if ln.strip().startswith("- [")]
    assert lines[0].startswith("- [08:00]")
    assert lines[1].startswith("- [09:00]")
    assert lines[2].startswith("- [10:00]")

    # Tags merged
    assert "daily-notes" in merged
    assert "child-tag" in merged


def test_vault_unset_merges_deduplicates_entries(tmp_path: Path, monkeypatch):
    """Duplicate entries across vaults are deduplicated during merge."""
    runner = CliRunner()

    parent_storage = tmp_path / "parent_vault"
    parent_storage.mkdir()
    (parent_storage / "daily").mkdir()
    (parent_storage / "notes").mkdir()
    (parent_storage / ".pkm").mkdir()

    child_storage = tmp_path / "child_vault"
    child_storage.mkdir()
    (child_storage / "daily").mkdir()
    (child_storage / "notes").mkdir()
    (child_storage / ".pkm").mkdir()

    parent_project = tmp_path / "parent_project"
    parent_project.mkdir()
    (parent_project / ".pkm").write_text('vault = "parent_vault"')

    child_project = parent_project / "child_project"
    child_project.mkdir()
    (child_project / ".pkm").write_text('vault = "child_vault"')

    same_entry = "- [09:00] same entry in both"
    (parent_storage / "daily" / "2026-04-16.md").write_text(
        f"---\nid: 2026-04-16\ntags: []\n---\n{same_entry}\n",
        encoding="utf-8",
    )
    (child_storage / "daily" / "2026-04-16.md").write_text(
        f"---\nid: 2026-04-16\ntags: []\n---\n{same_entry}\n- [10:00] unique child\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("pkm.config.get_vaults_root", lambda: tmp_path)
    monkeypatch.setattr("pkm.config.get_local_config_vault", lambda: "child_vault")
    monkeypatch.chdir(child_project)

    result = runner.invoke(main, ["vault", "unset"])
    assert result.exit_code == 0, result.output

    merged = (parent_storage / "daily" / "2026-04-16.md").read_text(encoding="utf-8")
    entries = [ln.strip() for ln in merged.splitlines() if ln.strip().startswith("- [")]
    # Same entry appears only once
    assert entries.count(same_entry) == 1
    assert len(entries) == 2  # same_entry + unique child


def test_vault_unset_remove_flag(tmp_path: Path, monkeypatch):
    runner = CliRunner()

    child_storage = tmp_path / "child_vault"
    child_storage.mkdir()
    (child_storage / "daily").mkdir()

    child_project = tmp_path / "child_project"
    child_project.mkdir()
    (child_project / ".pkm").write_text('vault = "child_vault"')

    monkeypatch.setattr("pkm.config.get_vaults_root", lambda: tmp_path)
    monkeypatch.setattr("pkm.config.get_local_config_vault", lambda: "child_vault")
    monkeypatch.chdir(child_project)

    result = runner.invoke(main, ["vault", "unset", "--remove"])
    assert result.exit_code == 0, result.output
    assert "Removed vault child_vault and deleted .pkm" in result.output
    assert not (child_project / ".pkm").exists()
