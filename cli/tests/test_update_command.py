from __future__ import annotations

from contextlib import contextmanager
import sys
from types import SimpleNamespace

from click.testing import CliRunner

import pkm.commands.update as update_mod
from pkm.commands.update import update_cmd


def _runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


def _make_repo(tmp_path):
    repo = tmp_path / "repo"
    cli_dir = repo / "cli"
    cli_dir.mkdir(parents=True)
    (cli_dir / "pyproject.toml").write_text("[project]\nname = 'pkm'\n")
    (repo / ".git").mkdir()
    return repo, cli_dir


class CommandDispatcher:
    def __init__(self, handlers=None):
        self.handlers = handlers or {}
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, cmd, **kwargs):
        cmd = list(cmd)
        self.calls.append((cmd, kwargs))
        key = tuple(cmd)
        handler = self.handlers.get(key)
        if handler is None:
            if cmd[0] == "git" and cmd[3:] == ["branch", "--show-current"]:
                return SimpleNamespace(returncode=0, stdout="main\n", stderr="")
            if cmd == ["pkm", "--version"]:
                return SimpleNamespace(returncode=0, stdout="pkm v9.9.9\n", stderr="")
            raise AssertionError(f"Unexpected subprocess command: {cmd}")
        if callable(handler):
            return handler(cmd, kwargs)
        return handler

    def commands(self) -> list[list[str]]:
        return [cmd for cmd, _kwargs in self.calls]


def _patch_post_install(monkeypatch):
    calls = []
    monkeypatch.setattr(update_mod, "_extra_installed", lambda _probe: False)
    monkeypatch.setattr(
        update_mod, "install_skill_files", lambda: calls.append("skills")
    )
    monkeypatch.setattr(
        update_mod, "install_shell_aliases", lambda: calls.append("aliases")
    )
    monkeypatch.setattr(update_mod, "sync_existing_web_unit", lambda: None)
    return calls


def test_update_helpers_normalize_tags_and_detect_installed_extras(monkeypatch):
    """Helper behavior keeps version tags and optional extras consistent."""
    assert update_mod._normalize_tag("1.2.3") == "v1.2.3"
    assert update_mod._normalize_tag("v1.2.3") == "v1.2.3"

    monkeypatch.setattr(update_mod, "_extra_installed", lambda _probe: True)
    assert update_mod._extra_installed("sentence_transformers") is True
    assert update_mod._extras_suffix() == "[search]"

    monkeypatch.setattr(update_mod, "_extra_installed", lambda _probe: False)
    assert update_mod._extra_installed("sentence_transformers") is False
    assert update_mod._extras_suffix() == ""


def test_update_extra_probe_does_not_import_module(monkeypatch, tmp_path):
    """Broken optional packages are still preserved when their module exists."""
    package_dir = tmp_path / "sentence_transformers"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("raise RuntimeError('broken import')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("sentence_transformers", None)

    assert update_mod._extra_installed("sentence_transformers") is True


def test_update_local_git_latest_reinstalls_editable_and_shows_changelog(
    monkeypatch, tmp_path
):
    """A local checkout pulls, reinstalls editable source, syncs hooks, and shows changes."""
    repo, cli_dir = _make_repo(tmp_path)
    (repo / "CHANGELOG.md").write_text(
        "\n## v2.74.0\n\n- New feature\n\n## v2.73.1\n\n- Current\n",
        encoding="utf-8",
    )
    hooks = _patch_post_install(monkeypatch)
    monkeypatch.setattr(update_mod, "find_local_cli_dir", lambda: cli_dir)
    monkeypatch.setattr("pkm.__version__", "2.73.1")

    dispatcher = CommandDispatcher(
        {
            ("git", "-C", str(repo), "pull", "--ff-only"): SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
            (
                "uv",
                "tool",
                "install",
                "--editable",
                str(cli_dir),
                "--reinstall-package",
                "pkm",
            ): SimpleNamespace(returncode=0, stdout="", stderr=""),
        }
    )
    monkeypatch.setattr(update_mod.subprocess, "run", dispatcher)

    result = _runner().invoke(update_cmd, [])

    assert result.exit_code == 0
    assert "pkm updated" in result.output
    assert "Changes since v2.73.1" in result.output
    assert "Now running: pkm v9.9.9" in result.output
    assert hooks == ["skills", "aliases"]
    assert ["git", "-C", str(repo), "pull", "--ff-only"] in dispatcher.commands()


def test_update_syncs_existing_web_unit_after_success(monkeypatch, tmp_path):
    """Successful updates refresh an installed pkm-web systemd unit."""
    repo, cli_dir = _make_repo(tmp_path)
    hooks = _patch_post_install(monkeypatch)
    unit_path = tmp_path / "pkm-web.service"
    monkeypatch.setattr(update_mod, "find_local_cli_dir", lambda: cli_dir)
    monkeypatch.setattr(update_mod, "sync_existing_web_unit", lambda: unit_path)

    dispatcher = CommandDispatcher(
        {
            ("git", "-C", str(repo), "pull", "--ff-only"): SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
            (
                "uv",
                "tool",
                "install",
                "--editable",
                str(cli_dir),
                "--reinstall-package",
                "pkm",
            ): SimpleNamespace(returncode=0, stdout="", stderr=""),
        }
    )
    monkeypatch.setattr(update_mod.subprocess, "run", dispatcher)

    result = _runner().invoke(update_cmd, [])

    assert result.exit_code == 0
    assert "PKM web unit synced" in result.output
    assert str(unit_path) in result.output
    assert hooks == ["skills", "aliases"]


def test_update_local_git_latest_defaults_to_main_worktree(monkeypatch, tmp_path):
    """A feature-worktree install updates from the main worktree by default."""
    feature_repo, feature_cli_dir = _make_repo(tmp_path / "feature")
    main_repo, main_cli_dir = _make_repo(tmp_path / "main")
    (main_repo / "CHANGELOG.md").write_text(
        "\n## v2.74.0\n\n- New feature\n\n## v2.73.1\n\n- Current\n",
        encoding="utf-8",
    )
    hooks = _patch_post_install(monkeypatch)
    monkeypatch.setattr(update_mod, "find_local_cli_dir", lambda: feature_cli_dir)
    monkeypatch.setattr("pkm.__version__", "2.73.1")

    dispatcher = CommandDispatcher(
        {
            (
                "git",
                "-C",
                str(feature_repo),
                "branch",
                "--show-current",
            ): SimpleNamespace(returncode=0, stdout="feat/pkm-webapp\n", stderr=""),
            (
                "git",
                "-C",
                str(feature_repo),
                "worktree",
                "list",
                "--porcelain",
            ): SimpleNamespace(
                returncode=0,
                stdout=(
                    f"worktree {main_repo}\n"
                    "HEAD abc123\n"
                    "branch refs/heads/main\n\n"
                    f"worktree {feature_repo}\n"
                    "HEAD def456\n"
                    "branch refs/heads/feat/pkm-webapp\n"
                ),
                stderr="",
            ),
            ("git", "-C", str(main_repo), "pull", "--ff-only"): SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
            (
                "uv",
                "tool",
                "install",
                "--editable",
                str(main_cli_dir),
                "--reinstall-package",
                "pkm",
            ): SimpleNamespace(returncode=0, stdout="", stderr=""),
        }
    )
    monkeypatch.setattr(update_mod.subprocess, "run", dispatcher)

    result = _runner().invoke(update_cmd, [])

    assert result.exit_code == 0
    assert "Using main worktree" in result.output
    assert ["git", "-C", str(main_repo), "pull", "--ff-only"] in dispatcher.commands()
    assert ["git", "-C", str(feature_repo), "pull", "--ff-only"] not in dispatcher.commands()
    assert hooks == ["skills", "aliases"]


def test_update_local_git_dev_current_branch_keeps_feature_worktree(
    monkeypatch, tmp_path
):
    """Development updates can still pull the currently installed branch explicitly."""
    repo, cli_dir = _make_repo(tmp_path)
    hooks = _patch_post_install(monkeypatch)
    monkeypatch.setattr(update_mod, "find_local_cli_dir", lambda: cli_dir)

    dispatcher = CommandDispatcher(
        {
            ("git", "-C", str(repo), "pull", "--ff-only"): SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
            (
                "uv",
                "tool",
                "install",
                "--editable",
                str(cli_dir),
                "--reinstall-package",
                "pkm",
            ): SimpleNamespace(returncode=0, stdout="", stderr=""),
        }
    )
    monkeypatch.setattr(update_mod.subprocess, "run", dispatcher)

    result = _runner().invoke(update_cmd, ["--dev-current-branch"])

    assert result.exit_code == 0
    assert ["git", "-C", str(repo), "pull", "--ff-only"] in dispatcher.commands()
    assert not any(cmd[:4] == ["git", "-C", str(repo), "branch"] for cmd in dispatcher.commands())
    assert hooks == ["skills", "aliases"]


def test_update_feature_worktree_without_main_worktree_fails_with_dev_hint(
    monkeypatch, tmp_path
):
    """Default update refuses to mutate a feature worktree when main is unavailable."""
    repo, cli_dir = _make_repo(tmp_path)
    hooks = _patch_post_install(monkeypatch)
    monkeypatch.setattr(update_mod, "find_local_cli_dir", lambda: cli_dir)

    dispatcher = CommandDispatcher(
        {
            (
                "git",
                "-C",
                str(repo),
                "branch",
                "--show-current",
            ): SimpleNamespace(returncode=0, stdout="feat/pkm-webapp\n", stderr=""),
            (
                "git",
                "-C",
                str(repo),
                "worktree",
                "list",
                "--porcelain",
            ): SimpleNamespace(
                returncode=0,
                stdout=(
                    f"worktree {repo}\n"
                    "HEAD def456\n"
                    "branch refs/heads/feat/pkm-webapp\n"
                ),
                stderr="",
            ),
        }
    )
    monkeypatch.setattr(update_mod.subprocess, "run", dispatcher)

    result = _runner().invoke(update_cmd, [])

    assert result.exit_code == 1
    assert "defaults to the main worktree" in result.stderr
    assert "--dev-current-branch" in result.stderr
    assert ["git", "-C", str(repo), "pull", "--ff-only"] not in dispatcher.commands()
    assert hooks == []


def test_update_local_git_specific_version_normalizes_checkout_tag(
    monkeypatch, tmp_path
):
    """A requested version fetches tags and checks out the normalized v-prefixed tag."""
    repo, cli_dir = _make_repo(tmp_path)
    hooks = _patch_post_install(monkeypatch)
    monkeypatch.setattr(update_mod, "find_local_cli_dir", lambda: cli_dir)

    dispatcher = CommandDispatcher(
        {
            ("git", "-C", str(repo), "fetch", "--tags"): SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
            ("git", "-C", str(repo), "checkout", "v1.2.3"): SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
            (
                "uv",
                "tool",
                "install",
                "--editable",
                str(cli_dir),
                "--reinstall-package",
                "pkm",
            ): SimpleNamespace(returncode=0, stdout="", stderr=""),
        }
    )
    monkeypatch.setattr(update_mod.subprocess, "run", dispatcher)

    result = _runner().invoke(update_cmd, ["1.2.3"])

    assert result.exit_code == 0
    assert ["git", "-C", str(repo), "checkout", "v1.2.3"] in dispatcher.commands()
    assert hooks == ["skills", "aliases"]


def test_update_checkout_failure_lists_remote_or_local_versions(monkeypatch, tmp_path):
    """Missing tags show available versions from GitHub or local git fallback."""
    repo, cli_dir = _make_repo(tmp_path)
    monkeypatch.setattr(update_mod, "find_local_cli_dir", lambda: cli_dir)
    monkeypatch.setattr(update_mod, "get_recent_versions", lambda _n: ["v2.0.0"])

    dispatcher = CommandDispatcher(
        {
            ("git", "-C", str(repo), "fetch", "--tags"): SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
            ("git", "-C", str(repo), "checkout", "v9.9.9"): SimpleNamespace(
                returncode=1, stdout="", stderr="missing"
            ),
        }
    )
    monkeypatch.setattr(update_mod.subprocess, "run", dispatcher)

    result = _runner().invoke(update_cmd, ["9.9.9"])

    assert result.exit_code == 1
    assert "Version v9.9.9 not found" in result.output
    assert "v2.0.0" in result.output
    assert "Could not checkout v9.9.9" in result.stderr

    monkeypatch.setattr(update_mod, "get_recent_versions", lambda _n: [])
    dispatcher = CommandDispatcher(
        {
            ("git", "-C", str(repo), "fetch", "--tags"): SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
            ("git", "-C", str(repo), "checkout", "v8.8.8"): SimpleNamespace(
                returncode=1, stdout="", stderr="missing"
            ),
            (
                "git",
                "-C",
                str(repo),
                "tag",
                "--sort=-version:refname",
            ): SimpleNamespace(
                returncode=0, stdout="v3.0.0\njunk\nv2.0.0\n", stderr=""
            ),
        }
    )
    monkeypatch.setattr(update_mod.subprocess, "run", dispatcher)

    result = _runner().invoke(update_cmd, ["8.8.8"])

    assert result.exit_code == 1
    assert "v3.0.0" in result.output
    assert "v2.0.0" in result.output


def test_update_local_git_failures_do_not_run_post_install_hooks(monkeypatch, tmp_path):
    """Pull, fetch, and uv failures stop before hook sync side effects."""
    repo, cli_dir = _make_repo(tmp_path)
    hooks = _patch_post_install(monkeypatch)
    monkeypatch.setattr(update_mod, "find_local_cli_dir", lambda: cli_dir)

    dispatcher = CommandDispatcher(
        {
            ("git", "-C", str(repo), "pull", "--ff-only"): SimpleNamespace(
                returncode=1, stdout="", stderr="diverged"
            ),
        }
    )
    monkeypatch.setattr(update_mod.subprocess, "run", dispatcher)
    result = _runner().invoke(update_cmd, [])
    assert result.exit_code == 1
    assert "git pull --ff-only failed" in result.stderr
    assert hooks == []

    dispatcher = CommandDispatcher(
        {
            ("git", "-C", str(repo), "fetch", "--tags"): SimpleNamespace(
                returncode=1, stdout="", stderr="network"
            ),
        }
    )
    monkeypatch.setattr(update_mod.subprocess, "run", dispatcher)
    result = _runner().invoke(update_cmd, ["1.2.3"])
    assert result.exit_code == 1
    assert "git fetch failed" in result.stderr
    assert hooks == []

    dispatcher = CommandDispatcher(
        {
            ("git", "-C", str(repo), "pull", "--ff-only"): SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
            (
                "uv",
                "tool",
                "install",
                "--editable",
                str(cli_dir),
                "--reinstall-package",
                "pkm",
            ): SimpleNamespace(returncode=2, stdout="", stderr="uv failed"),
        }
    )
    monkeypatch.setattr(update_mod.subprocess, "run", dispatcher)
    result = _runner().invoke(update_cmd, [])
    assert result.exit_code == 1
    assert "uv tool install failed" in result.stderr
    assert hooks == []


def test_update_non_git_version_refusal_and_tarball_install(monkeypatch, tmp_path):
    """Non-git installs reject pinned versions but can reinstall downloaded source."""
    hooks = _patch_post_install(monkeypatch)
    monkeypatch.setattr(update_mod, "find_local_cli_dir", lambda: None)

    result = _runner().invoke(update_cmd, ["1.2.3"])
    assert result.exit_code == 1
    assert "Specific version installs require a local git checkout" in result.stderr
    assert hooks == []

    downloaded = tmp_path / "downloaded-cli"
    downloaded.mkdir()

    @contextmanager
    def fake_cli_source():
        yield downloaded, False

    monkeypatch.setattr(update_mod, "cli_source", fake_cli_source)
    dispatcher = CommandDispatcher(
        {
            (
                "uv",
                "tool",
                "install",
                str(downloaded),
                "--reinstall-package",
                "pkm",
            ): SimpleNamespace(returncode=0, stdout="", stderr=""),
        }
    )
    monkeypatch.setattr(update_mod.subprocess, "run", dispatcher)

    result = _runner().invoke(update_cmd, [])

    assert result.exit_code == 0
    assert "Downloading latest from GitHub" in result.output
    assert "pkm updated" in result.output
    assert hooks == ["skills", "aliases"]


def test_update_non_git_download_and_install_failures(monkeypatch, tmp_path):
    """Download/source and uv failures become Click errors with no hook sync."""
    hooks = _patch_post_install(monkeypatch)
    monkeypatch.setattr(update_mod, "find_local_cli_dir", lambda: None)

    @contextmanager
    def broken_cli_source():
        raise RuntimeError("download failed")
        yield

    monkeypatch.setattr(update_mod, "cli_source", broken_cli_source)
    result = _runner().invoke(update_cmd, [])
    assert result.exit_code == 1
    assert "download failed" in result.stderr
    assert hooks == []

    downloaded = tmp_path / "downloaded-cli"
    downloaded.mkdir()

    @contextmanager
    def fake_cli_source():
        yield downloaded, False

    monkeypatch.setattr(update_mod, "cli_source", fake_cli_source)
    dispatcher = CommandDispatcher(
        {
            (
                "uv",
                "tool",
                "install",
                str(downloaded),
                "--reinstall-package",
                "pkm",
            ): SimpleNamespace(returncode=1, stdout="", stderr="uv failed"),
        }
    )
    monkeypatch.setattr(update_mod.subprocess, "run", dispatcher)

    result = _runner().invoke(update_cmd, [])
    assert result.exit_code == 1
    assert "uv tool install failed" in result.stderr
    assert hooks == []
