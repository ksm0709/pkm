from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig

import pkm.commands.setup as setup_mod


def _runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


def _successful_run(*_args, **_kwargs):
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_sync_dir_replaces_stale_destination_tree(tmp_path: Path) -> None:
    """Syncing skill assets removes stale files/dirs before copying the current tree."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "commands").mkdir(parents=True)
    (src / "SKILL.md").write_text("current skill", encoding="utf-8")
    (src / "commands" / "setup.md").write_text("current command", encoding="utf-8")

    (dst / "old-dir").mkdir(parents=True)
    (dst / "old-dir" / "stale.md").write_text("stale", encoding="utf-8")
    (dst / "old-file.md").write_text("stale", encoding="utf-8")

    setup_mod._sync_dir(src, dst)

    assert not (dst / "old-dir").exists()
    assert not (dst / "old-file.md").exists()
    assert (dst / "SKILL.md").read_text(encoding="utf-8") == "current skill"
    assert (dst / "commands" / "setup.md").read_text(
        encoding="utf-8"
    ) == "current command"


def test_find_skill_src_uses_local_checkout_plugin_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prefer a local plugin tree, then fall back to packaged skill assets."""
    repo = tmp_path / "repo"
    cli_dir = repo / "cli"
    skill_dir = repo / "plugin" / "skills" / "pkm"
    skill_dir.mkdir(parents=True)
    cli_dir.mkdir()

    monkeypatch.setattr("pkm._install_source.find_local_cli_dir", lambda: cli_dir)
    assert setup_mod._find_skill_src() == skill_dir

    skill_dir.rmdir()
    packaged = Path(setup_mod.__file__).resolve().parents[1] / "_bundled_skill"
    assert setup_mod._find_skill_src() == packaged


def test_install_skill_files_syncs_agent_and_command_surfaces(
    tmp_path: Path, mock_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skill installation mirrors current plugin files and prunes stale agent commands."""
    skill_src = tmp_path / "plugin" / "skills" / "pkm"
    commands_src = skill_src / "commands" / "pkm"
    commands_src.mkdir(parents=True)
    (skill_src / "SKILL.md").write_text("current skill", encoding="utf-8")
    (commands_src / "daily.md").write_text("current command", encoding="utf-8")

    stale_skill = mock_home / ".claude" / "skills" / "pkm" / "stale.md"
    stale_skill.parent.mkdir(parents=True)
    stale_skill.write_text("stale", encoding="utf-8")
    stale_command = mock_home / ".agents" / "commands" / "pkm" / "old.md"
    stale_command.parent.mkdir(parents=True)
    stale_command.write_text("stale", encoding="utf-8")

    monkeypatch.setattr(setup_mod, "_find_skill_src", lambda: skill_src)

    assert setup_mod.install_skill_files() is True

    for root in (mock_home / ".claude", mock_home / ".agents"):
        assert (root / "skills" / "pkm" / "SKILL.md").read_text(
            encoding="utf-8"
        ) == "current skill"
        assert (root / "commands" / "pkm" / "daily.md").read_text(
            encoding="utf-8"
        ) == "current command"
    assert not stale_skill.exists()
    assert not stale_command.exists()


def test_install_skill_files_reports_missing_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing packaged skill assets skip sync instead of creating partial installs."""
    monkeypatch.setattr(setup_mod, "_find_skill_src", lambda: None)

    assert setup_mod.install_skill_files() is False


def test_wheel_install_finds_and_syncs_real_bundled_skill_files(tmp_path: Path) -> None:
    """A non-editable wheel install can sync the repository's real PKM skill tree."""
    cli_dir = Path(__file__).resolve().parents[1]
    dist_dir = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--out-dir", str(dist_dir)],
        cwd=cli_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(dist_dir.glob("pkm-*.whl"))
    site_dir = tmp_path / "installed"
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--offline",
            "--no-deps",
            "--target",
            str(site_dir),
            str(wheel),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    home = tmp_path / "home"
    script = """
from pathlib import Path
import os
import pkm
import pkm._install_source
from pkm.commands.setup import _find_skill_src, install_skill_files

assert Path(pkm.__file__).is_relative_to(Path(os.environ["PKM_TEST_SITE_DIR"]))
pkm._install_source.find_local_cli_dir = lambda: None
source = _find_skill_src()
assert source is not None
required = (
    "SKILL.md",
    "AGENTS.md",
    "diagnosis/SKILL.md",
    "workflows/AGENTS.md",
    "workflows/zettelkasten-maintenance.md",
)
for relative in required:
    assert source.joinpath(*relative.split("/")).is_file(), relative
assert install_skill_files() is True
home = Path.home()
for root in (home / ".claude", home / ".agents"):
    installed = root / "skills" / "pkm"
    for relative in required:
        assert installed.joinpath(*relative.split("/")).is_file(), relative
"""
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={
            **os.environ,
            "HOME": str(home),
            "PKM_TEST_SITE_DIR": str(site_dir),
            "PYTHONPATH": str(site_dir),
        },
        check=True,
        capture_output=True,
        text=True,
    )


def test_load_setup_choices_requires_complete_saved_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Saved setup choices are reusable only when every prompt answer is present."""
    monkeypatch.setattr(
        setup_mod,
        "load_config",
        lambda: {"setup": {"install_search": True, "vaults_root": "/vaults"}},
    )
    assert setup_mod._load_setup_choices() is None

    saved = {
        "install_search": "true",
        "install_dev": "false",
        "vaults_root": "/vaults",
        "default_vault": "notes",
    }
    monkeypatch.setattr(setup_mod, "load_config", lambda: {"setup": saved})
    assert setup_mod._load_setup_choices() == saved


def test_save_config_merged_preserves_sections_and_serializes_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Saving setup choices merges them with existing sections and writes TOML booleans."""
    config_path = tmp_path / "config" / "pkm" / "config"
    monkeypatch.setattr(setup_mod, "CONFIG_PATH", config_path)
    monkeypatch.setattr(
        setup_mod,
        "load_config",
        lambda: {"api": {"host": "127.0.0.1"}, "defaults": {"vault": "old"}},
    )

    setup_mod._save_config_merged(
        setup_choices={
            "install_search": True,
            "install_dev": False,
            "vaults_root": str(tmp_path / "vaults"),
            "default_vault": "notes",
        },
        default_vault="notes",
    )

    text = config_path.read_text(encoding="utf-8")
    assert '[api]\nhost = "127.0.0.1"' in text
    assert "[setup]" in text
    assert "install_search = true" in text
    assert "install_dev = false" in text
    assert '[defaults]\nvault = "notes"' in text


def test_check_linger_parses_enabled_and_defaults_malformed_to_no(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The web setup linger gate accepts only loginctl output with a Linger key."""
    monkeypatch.setenv("USER", "testuser")
    monkeypatch.setattr(
        setup_mod.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="Linger=yes\n"),
    )
    assert setup_mod._check_linger() == "yes"

    monkeypatch.setattr(
        setup_mod.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="State=active\n"),
    )
    assert setup_mod._check_linger() == "no"


def test_setup_reuses_saved_choices_without_prompting_for_vaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Accepting saved setup choices skips discovery/init and installs saved extras."""
    saved = {
        "install_search": "true",
        "install_dev": "true",
        "vaults_root": str(tmp_path / "vaults"),
        "default_vault": "work",
    }
    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()
    save = MagicMock()
    discover = MagicMock(return_value={})
    init = MagicMock()
    run = MagicMock(return_value=SimpleNamespace(returncode=0))

    @contextmanager
    def fake_cli_source():
        yield cli_dir, True

    monkeypatch.setattr(setup_mod, "_load_setup_choices", lambda: saved)
    monkeypatch.setattr(setup_mod, "discover_vaults", discover)
    monkeypatch.setattr(setup_mod, "init_vault_dirs", init)
    monkeypatch.setattr(setup_mod, "_save_config_merged", save)
    monkeypatch.setattr(setup_mod, "install_skill_files", lambda: True)
    monkeypatch.setattr(setup_mod, "install_shell_aliases", lambda: None)
    monkeypatch.setattr(setup_mod.subprocess, "run", run)
    monkeypatch.setattr("pkm._install_source.cli_source", fake_cli_source)

    result = _runner().invoke(main, ["setup"], input="y\n")

    assert result.exit_code == 0, result.output
    discover.assert_not_called()
    init.assert_not_called()
    save.assert_called_once()
    assert run.call_args.args[0] == [
        "uv",
        "tool",
        "install",
        "--editable",
        f"{cli_dir}[search,dev]",
        "--reinstall-package",
        "pkm",
    ]


def test_setup_existing_vault_prompt_creates_missing_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Choosing a default vault outside discovered vaults creates it and records it."""
    vaults_root = tmp_path / "vaults"
    existing = {"old": VaultConfig(name="old", path=vaults_root / "old")}
    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()
    init = MagicMock()
    save = MagicMock()

    @contextmanager
    def fake_cli_source():
        yield cli_dir, True

    monkeypatch.setattr(setup_mod, "_load_setup_choices", lambda: None)
    monkeypatch.setattr(setup_mod, "discover_vaults", lambda _root=None: existing)
    monkeypatch.setattr(setup_mod, "init_vault_dirs", init)
    monkeypatch.setattr(setup_mod, "_save_config_merged", save)
    monkeypatch.setattr(setup_mod, "install_skill_files", lambda: True)
    monkeypatch.setattr(setup_mod, "install_shell_aliases", lambda: None)
    monkeypatch.setattr(setup_mod.subprocess, "run", _successful_run)
    monkeypatch.setattr("pkm._install_source.cli_source", fake_cli_source)

    result = _runner().invoke(
        main,
        ["setup"],
        input=f"n\nn\n{vaults_root}\nnew-default\n",
    )

    assert result.exit_code == 0, result.output
    assert "not found" in result.output
    init.assert_called_once_with(vaults_root / "new-default", "new-default")
    assert save.call_args.kwargs["default_vault"] == "new-default"


def test_setup_rejects_invalid_new_vault_before_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An invalid new vault name aborts before dependency installation side effects."""
    run = MagicMock()
    monkeypatch.setattr(setup_mod, "_load_setup_choices", lambda: None)
    monkeypatch.setattr(setup_mod, "discover_vaults", lambda _root=None: {})
    monkeypatch.setattr(setup_mod.subprocess, "run", run)

    result = _runner().invoke(
        main,
        ["setup"],
        input=f"n\nn\n{tmp_path / 'vaults'}\nbad/name\n",
    )

    assert result.exit_code == 1
    assert "Invalid vault name" in result.stderr
    run.assert_not_called()


def test_setup_remote_source_installs_without_editable_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remote source setup announces download and installs the resolved path non-editably."""
    downloaded = tmp_path / "downloaded-cli"
    downloaded.mkdir()
    run = MagicMock(return_value=SimpleNamespace(returncode=0))

    @contextmanager
    def fake_cli_source():
        yield downloaded, False

    monkeypatch.setattr(setup_mod, "_load_setup_choices", lambda: None)
    monkeypatch.setattr(setup_mod, "discover_vaults", lambda _root=None: {})
    monkeypatch.setattr(setup_mod, "init_vault_dirs", lambda *_args: None)
    monkeypatch.setattr(setup_mod, "_save_config_merged", lambda **_kwargs: None)
    monkeypatch.setattr(setup_mod, "install_skill_files", lambda: True)
    monkeypatch.setattr(setup_mod, "install_shell_aliases", lambda: None)
    monkeypatch.setattr(setup_mod.subprocess, "run", run)
    monkeypatch.setattr("pkm._install_source.cli_source", fake_cli_source)

    result = _runner().invoke(
        main,
        ["setup"],
        input=f"y\nn\n{tmp_path / 'vaults'}\nnotes\n",
    )

    assert result.exit_code == 0, result.output
    assert "Downloading latest source from GitHub" in result.output
    assert run.call_args.args[0] == [
        "uv",
        "tool",
        "install",
        f"{downloaded}[search]",
        "--reinstall-package",
        "pkm",
    ]


def test_setup_dependency_and_source_failures_stop_before_post_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Download/source and uv failures abort without saving config or syncing skills."""
    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()
    save = MagicMock()
    skills = MagicMock()

    @contextmanager
    def fake_cli_source():
        yield cli_dir, True

    monkeypatch.setattr(setup_mod, "_load_setup_choices", lambda: None)
    monkeypatch.setattr(setup_mod, "discover_vaults", lambda _root=None: {})
    monkeypatch.setattr(setup_mod, "init_vault_dirs", lambda *_args: None)
    monkeypatch.setattr(setup_mod, "_save_config_merged", save)
    monkeypatch.setattr(setup_mod, "install_skill_files", skills)
    monkeypatch.setattr(setup_mod, "install_shell_aliases", lambda: None)
    monkeypatch.setattr(
        setup_mod.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=7),
    )
    monkeypatch.setattr("pkm._install_source.cli_source", fake_cli_source)

    result = _runner().invoke(
        main,
        ["setup"],
        input=f"n\nn\n{tmp_path / 'vaults'}\nnotes\n",
    )

    assert result.exit_code == 1
    assert "Dependency installation failed" in result.stderr
    save.assert_not_called()
    skills.assert_not_called()

    @contextmanager
    def broken_cli_source():
        raise RuntimeError("source unavailable")
        yield

    monkeypatch.setattr("pkm._install_source.cli_source", broken_cli_source)
    result = _runner().invoke(
        main,
        ["setup"],
        input=f"n\nn\n{tmp_path / 'vaults'}\nnotes\n",
    )

    assert result.exit_code == 1
    assert "source unavailable" in result.stderr
    save.assert_not_called()
    skills.assert_not_called()


def test_setup_warns_when_skill_files_are_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful setup still finishes when optional packaged skill files are absent."""
    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()

    @contextmanager
    def fake_cli_source():
        yield cli_dir, True

    monkeypatch.setattr(setup_mod, "_load_setup_choices", lambda: None)
    monkeypatch.setattr(setup_mod, "discover_vaults", lambda _root=None: {})
    monkeypatch.setattr(setup_mod, "init_vault_dirs", lambda *_args: None)
    monkeypatch.setattr(setup_mod, "_save_config_merged", lambda **_kwargs: None)
    monkeypatch.setattr(setup_mod, "install_skill_files", lambda: False)
    monkeypatch.setattr(setup_mod, "install_shell_aliases", lambda: None)
    monkeypatch.setattr(setup_mod.subprocess, "run", _successful_run)
    monkeypatch.setattr("pkm._install_source.cli_source", fake_cli_source)

    result = _runner().invoke(
        main,
        ["setup"],
        input=f"n\nn\n{tmp_path / 'vaults'}\nnotes\n",
    )

    assert result.exit_code == 0, result.output
    assert "Skill files not found" in result.output
    assert "Setup complete" in result.output


def test_web_setup_rechecks_linger_after_user_confirmation(
    mock_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Confirming remediation is insufficient when loginctl still reports disabled linger."""
    calls = iter(
        [
            SimpleNamespace(stdout="Linger=no\n"),
            SimpleNamespace(stdout="Linger=no\n"),
        ]
    )
    monkeypatch.setenv("USER", "testuser")
    monkeypatch.setattr(
        setup_mod.subprocess, "run", lambda *_args, **_kwargs: next(calls)
    )

    result = _runner().invoke(main, ["setup", "--web"], input="y\n")

    assert result.exit_code == 1
    assert "Linger is still disabled" in result.stderr
    assert not (mock_home / ".config" / "pkm" / "web-token").exists()
    assert not (mock_home / ".config" / "systemd" / "user" / "pkm-web.service").exists()


def test_web_setup_empty_password_aborts_before_private_files(
    mock_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blank browser password fails closed before token, password, or unit files exist."""
    monkeypatch.setenv("USER", "testuser")
    monkeypatch.setattr(
        setup_mod.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="Linger=yes\n"),
    )
    monkeypatch.setattr(setup_mod.click, "prompt", lambda *_args, **_kwargs: "")

    result = _runner().invoke(main, ["setup", "--web"])

    assert result.exit_code == 1
    assert "Password cannot be empty" in result.stderr
    assert not (mock_home / ".config" / "pkm" / "web-token").exists()
    assert not (mock_home / ".config" / "pkm" / "web-password").exists()
    assert not (mock_home / ".config" / "systemd" / "user" / "pkm-web.service").exists()


def test_web_setup_preserves_existing_token_and_reset_rotates_it(
    mock_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Normal web setup keeps an existing bearer token; reset rotates it and marks sessions."""
    token_path = mock_home / ".config" / "pkm" / "web-token"
    token_path.parent.mkdir(parents=True)
    token_path.write_text("existing-token\n", encoding="utf-8")
    token_path.chmod(0o644)

    monkeypatch.setenv("USER", "testuser")
    monkeypatch.setattr(
        setup_mod.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="Linger=yes\n"),
    )
    monkeypatch.setattr(setup_mod, "_prompt_password", lambda: "secret")
    monkeypatch.setattr(
        "pkm.web.auth.hash_password", lambda password: f"hashed:{password}"
    )
    monkeypatch.setattr(setup_mod.secrets, "token_hex", lambda _n: "rotated-token")
    monkeypatch.setattr(setup_mod.time, "time_ns", lambda: 123456789)

    result = _runner().invoke(main, ["setup", "--web"])

    assert result.exit_code == 0, result.output
    assert token_path.read_text(encoding="utf-8").strip() == "existing-token"
    assert (token_path.stat().st_mode & 0o777) == 0o600
    assert "PKM_WEB_TOKEN=existing-token" in result.output
    assert not (mock_home / ".config" / "pkm" / "web-session-reset").exists()

    result = _runner().invoke(main, ["setup", "--web", "--reset"])

    assert result.exit_code == 0, result.output
    assert token_path.read_text(encoding="utf-8") == "rotated-token"
    assert (mock_home / ".config" / "pkm" / "web-session-reset").read_text(
        encoding="utf-8"
    ) == "123456789"
