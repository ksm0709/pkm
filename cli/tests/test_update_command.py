from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import click
from click.testing import CliRunner
import pytest

from pkm import cli as cli_mod
import pkm.commands.setup as setup_mod
import pkm.commands.update as update_mod
import pkm.workflows as workflows_mod
from pkm.cli import main
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
            if cmd in (["pkm", "--version"], ["/installed/bin/pkm", "--version"]):
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
    monkeypatch.setattr(update_mod, "load_config", lambda: {})
    monkeypatch.setattr(
        update_mod, "_resolve_current_pkm_executable", lambda: Path("/installed/bin/pkm")
    )
    monkeypatch.setattr(
        update_mod,
        "_run_fresh_post_update",
        lambda _executable, _prev_version: calls.append("post-update"),
    )
    return calls


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_resolve_current_pkm_executable_prefers_direct_absolute_invocation(
    monkeypatch, tmp_path
):
    """An explicitly invoked pkm remains selected even when PATH has no pkm."""
    direct = _make_executable(tmp_path / "direct" / "pkm")
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))

    assert update_mod._resolve_current_pkm_executable(str(direct)) == direct.resolve()


def test_resolve_current_pkm_executable_does_not_select_competing_path_entry(
    monkeypatch, tmp_path
):
    """A stale PATH pkm cannot replace the directly invoked current entrypoint."""
    direct = _make_executable(tmp_path / "current" / "pkm")
    stale = _make_executable(tmp_path / "stale" / "pkm")
    monkeypatch.setenv("PATH", os.pathsep.join((str(stale.parent), str(direct.parent))))

    assert update_mod._resolve_current_pkm_executable(str(direct)) == direct.resolve()


def test_resolve_current_pkm_executable_prefers_dot_slash_invocation_over_path(
    monkeypatch, tmp_path
):
    """A ./pkm invocation preserves the executable selected from the current directory."""
    direct = _make_executable(tmp_path / "pkm")
    stale = _make_executable(tmp_path / "stale" / "pkm")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(stale.parent))

    selected = update_mod._resolve_current_pkm_executable("./pkm")

    assert selected == direct.absolute()


def test_resolve_current_pkm_executable_preserves_retargetable_symlink(
    monkeypatch, tmp_path
):
    """The saved entrypoint follows a reinstall that retargets its symlink."""
    first = _make_executable(tmp_path / "versions" / "first" / "pkm")
    first.write_text("#!/bin/sh\nprintf 'first\\n'\n", encoding="utf-8")
    second = _make_executable(tmp_path / "versions" / "second" / "pkm")
    second.write_text("#!/bin/sh\nprintf 'second\\n'\n", encoding="utf-8")
    entrypoint = tmp_path / "bin" / "pkm"
    entrypoint.parent.mkdir()
    entrypoint.symlink_to(first)
    monkeypatch.setenv("PATH", str(entrypoint.parent))

    selected = update_mod._resolve_current_pkm_executable(str(entrypoint))
    entrypoint.unlink()
    entrypoint.symlink_to(second)
    result = subprocess.run([str(selected)], capture_output=True, text=True, check=True)

    assert selected == entrypoint.absolute()
    assert selected.is_symlink()
    assert result.stdout == "second\n"


def test_resolve_current_pkm_executable_rejects_missing_direct_and_path(
    monkeypatch, tmp_path
):
    """A missing current executable fails before update mutation can begin."""
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))

    with pytest.raises(click.ClickException, match="current pkm executable"):
        update_mod._resolve_current_pkm_executable(str(tmp_path / "missing" / "pkm"))


def test_update_runs_post_update_in_fresh_installed_process_after_reinstall(
    monkeypatch, tmp_path
):
    """A successful reinstall delegates post-install sync to the installed CLI."""
    repo, cli_dir = _make_repo(tmp_path)
    monkeypatch.setattr(update_mod, "_extra_installed", lambda _probe: False)
    monkeypatch.setattr(update_mod, "load_config", lambda: {})
    monkeypatch.setattr(update_mod, "find_local_cli_dir", lambda: cli_dir)
    monkeypatch.setattr("pkm.__version__", "2.96.0")
    monkeypatch.setattr(
        update_mod,
        "_resolve_current_pkm_executable",
        lambda: Path("/installed/bin/pkm"),
    )

    install_command = [
        "uv",
        "tool",
        "install",
        "--editable",
        str(cli_dir),
        "--reinstall-package",
        "pkm",
    ]
    post_update_command = [
        "/installed/bin/pkm",
        "post-update",
        "--from-version",
        "2.96.0",
    ]
    dispatcher = CommandDispatcher(
        {
            ("git", "-C", str(repo), "pull", "--ff-only"): SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
            tuple(install_command): SimpleNamespace(returncode=0, stdout="", stderr=""),
            tuple(post_update_command): SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
        }
    )
    monkeypatch.setattr(update_mod.subprocess, "run", dispatcher)

    result = _runner().invoke(update_cmd, [])

    assert result.exit_code == 0, result.output
    assert dispatcher.commands().index(install_command) < dispatcher.commands().index(
        post_update_command
    )
    assert "pkm updated" in result.output


def test_update_post_update_failure_does_not_report_full_success(monkeypatch, tmp_path):
    """A failed fresh-process sync leaves the reinstall visibly incomplete."""
    repo, cli_dir = _make_repo(tmp_path)
    monkeypatch.setattr(update_mod, "_extra_installed", lambda _probe: False)
    monkeypatch.setattr(update_mod, "load_config", lambda: {})
    monkeypatch.setattr(update_mod, "find_local_cli_dir", lambda: cli_dir)
    monkeypatch.setattr("pkm.__version__", "2.96.0")
    monkeypatch.setattr(
        update_mod,
        "_resolve_current_pkm_executable",
        lambda: Path("/installed/bin/pkm"),
    )

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
            (
                "/installed/bin/pkm",
                "post-update",
                "--from-version",
                "2.96.0",
            ): SimpleNamespace(returncode=9, stdout="", stderr="sync failed"),
        }
    )
    monkeypatch.setattr(update_mod.subprocess, "run", dispatcher)

    result = _runner().invoke(update_cmd, [])

    assert result.exit_code == 1
    assert "post-update failed" in result.stderr
    assert "pkm updated" not in result.output


def test_post_update_is_idempotent_and_uses_runtime_imported_helpers(
    monkeypatch, tmp_path
):
    """The hidden command safely reruns every v2 post-install synchronization."""
    calls: list[str] = []
    unit_path = tmp_path / "pkm-web.service"
    workflow_path = tmp_path / "workflow.json"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli_mod, "available_update", lambda _version: None)
    monkeypatch.setattr(
        setup_mod, "install_skill_files", lambda: calls.append("skills") or True
    )
    monkeypatch.setattr(
        setup_mod, "install_shell_aliases", lambda: calls.append("aliases")
    )
    monkeypatch.setattr(
        setup_mod,
        "sync_existing_web_unit",
        lambda: calls.append("web-unit") or unit_path,
    )
    monkeypatch.setattr(
        workflows_mod,
        "sync_installed_workflow_defaults",
        lambda: calls.append("workflows") or workflow_path,
    )

    first = _runner().invoke(main, ["post-update", "--from-version", "2.96.0"])
    second = _runner().invoke(main, ["post-update", "--from-version", "2.96.0"])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert calls == [
        "skills",
        "aliases",
        "web-unit",
        "workflows",
        "skills",
        "aliases",
        "web-unit",
        "workflows",
    ]
    assert "Post-update synchronization complete" in first.output
    assert str(unit_path) in first.output
    assert str(workflow_path) in first.output


def test_post_update_surfaces_helper_failure(monkeypatch):
    """A helper error identifies the failed sync and returns non-zero."""
    monkeypatch.setattr(cli_mod, "available_update", lambda _version: None)
    monkeypatch.setattr(setup_mod, "install_skill_files", lambda: True)
    monkeypatch.setattr(
        setup_mod,
        "install_shell_aliases",
        lambda: (_ for _ in ()).throw(OSError("read-only shell config")),
    )

    result = _runner().invoke(main, ["post-update", "--from-version", "2.96.0"])

    assert result.exit_code == 1
    assert "shell aliases sync failed" in result.stderr
    assert "read-only shell config" in result.stderr
    assert "Post-update synchronization complete" not in result.output


def test_post_update_treats_missing_skill_assets_as_failure(monkeypatch):
    """A false skill-install result prevents the bridge from reporting success."""
    monkeypatch.setattr(cli_mod, "available_update", lambda _version: None)
    monkeypatch.setattr(setup_mod, "install_skill_files", lambda: False)

    result = _runner().invoke(main, ["post-update", "--from-version", "2.96.1"])

    assert result.exit_code == 1
    assert "skill files sync failed" in result.stderr
    assert "bundled PKM skill assets" in result.stderr
    assert "Post-update synchronization complete" not in result.output


@pytest.mark.parametrize("target", ["v2.96.0", "v2.96.1-rc.1"])
def test_update_blocks_pre_bridge_semver_before_subprocess_mutation(monkeypatch, target):
    """Rollback below v2.96.1 requires manual quarantine rather than self-update."""
    calls: list[list[str]] = []
    monkeypatch.setattr(
        update_mod.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(list(command)),
    )

    result = _runner().invoke(update_cmd, [target])

    assert result.exit_code == 1
    assert "v2.96.1" in result.stderr
    assert "stop/quarantine" in result.stderr
    assert "direct install" in result.stderr
    assert calls == []


@pytest.mark.parametrize(
    "target",
    [
        "2.96.0^{}",
        "2.96.0~0",
        "main",
        "2.96",
        "2.96.1-",
        "2.96.1+",
        "2.96.1..2",
        "v02.96.1",
    ],
)
def test_update_rejects_non_semver_target_before_resolution_or_mutation(
    monkeypatch, target
):
    """Explicit git revisions cannot bypass the safe tagged-release bridge."""
    resolver_calls: list[None] = []
    subprocess_calls: list[list[str]] = []
    monkeypatch.setattr(
        update_mod,
        "_resolve_current_pkm_executable",
        lambda: resolver_calls.append(None),
    )
    monkeypatch.setattr(
        update_mod.subprocess,
        "run",
        lambda command, **_kwargs: subprocess_calls.append(list(command)),
    )

    result = _runner().invoke(update_cmd, [target])

    assert result.exit_code == 1
    assert "semantic version" in result.stderr
    assert resolver_calls == []
    assert subprocess_calls == []


@pytest.mark.parametrize(
    "target",
    [
        "2.96.1",
        "v2.96.2",
        "2.96.1+build.7",
        "v3.0.0-rc.1+linux-x86-64",
    ],
)
def test_bridge_accepts_semver_release_targets_at_or_above_baseline(target):
    """Valid release tags retain optional v, prerelease, and build syntax."""
    update_mod._block_pre_bridge_downgrade(target)


def test_post_update_failure_retry_command_shell_quotes_executable_path(monkeypatch):
    """The suggested retry command remains safe to paste when argv contains spaces."""
    monkeypatch.setattr(
        update_mod.subprocess,
        "run",
        lambda _command: SimpleNamespace(returncode=9),
    )

    with pytest.raises(click.ClickException) as exc_info:
        update_mod._run_fresh_post_update(
            Path("/opt/PKM releases/current pkm"), "2.96.1"
        )

    assert (
        "Retry with: '/opt/PKM releases/current pkm' post-update "
        "--from-version 2.96.1" in str(exc_info.value)
    )


def test_update_helpers_normalize_tags_and_detect_installed_extras(monkeypatch):
    """Helper behavior keeps version tags and optional extras consistent."""
    assert update_mod._normalize_tag("1.2.3") == "v1.2.3"
    assert update_mod._normalize_tag("v1.2.3") == "v1.2.3"

    monkeypatch.setattr(update_mod, "load_config", lambda: {})
    monkeypatch.setattr(update_mod, "_extra_installed", lambda _probe: True)
    assert update_mod._extra_installed("sentence_transformers") is True
    assert update_mod._extras_suffix() == "[search]"

    monkeypatch.setattr(update_mod, "_extra_installed", lambda _probe: False)
    assert update_mod._extra_installed("sentence_transformers") is False
    assert update_mod._extras_suffix() == ""


def test_update_preserves_search_extra_from_saved_setup_when_probe_missing(
    monkeypatch,
):
    """Saved setup intent preserves search dependencies even if module probing fails."""
    monkeypatch.setattr(update_mod, "_extra_installed", lambda _probe: False)
    monkeypatch.setattr(
        update_mod, "load_config", lambda: {"setup": {"install_search": True}}
    )

    assert update_mod._extras_suffix() == "[search]"


def test_update_preserves_search_extra_from_string_setup_value(monkeypatch):
    """Config parsed as strings still preserves search extra across updates."""
    monkeypatch.setattr(update_mod, "_extra_installed", lambda _probe: False)
    monkeypatch.setattr(
        update_mod, "load_config", lambda: {"setup": {"install_search": "true"}}
    )

    assert update_mod._extras_suffix() == "[search]"


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
    assert hooks == ["post-update"]
    assert ["git", "-C", str(repo), "pull", "--ff-only"] in dispatcher.commands()


def test_update_module_does_not_cache_post_install_helpers():
    """The long-lived updater must not retain helper objects across reinstall."""
    stale_helper_names = {
        "install_skill_files",
        "install_shell_aliases",
        "sync_existing_web_unit",
        "sync_installed_workflow_defaults",
    }

    assert stale_helper_names.isdisjoint(vars(update_mod))


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
    assert hooks == ["post-update"]


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
    assert hooks == ["post-update"]


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
            ("git", "-C", str(repo), "checkout", "v2.96.2"): SimpleNamespace(
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

    result = _runner().invoke(update_cmd, ["2.96.2"])

    assert result.exit_code == 0
    assert ["git", "-C", str(repo), "checkout", "v2.96.2"] in dispatcher.commands()
    assert hooks == ["post-update"]


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
    result = _runner().invoke(update_cmd, ["2.96.2"])
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

    result = _runner().invoke(update_cmd, ["2.96.2"])
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
    assert hooks == ["post-update"]


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
