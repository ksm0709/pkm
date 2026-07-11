"""pkm update — pull latest or a specific version and reinstall."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path

import click
from rich.console import Console

from pkm._install_source import cli_source, find_local_cli_dir
from pkm.config import load_config
from pkm.version_check import get_recent_versions

console = Console()
_BRIDGE_BASELINE = (2, 96, 1)


def _normalize_tag(version: str) -> str:
    """Ensure version has a 'v' prefix (e.g. '0.3.0' → 'v0.3.0')."""
    return version if version.startswith("v") else f"v{version}"


def _semver_core(version: str) -> tuple[int, int, int] | None:
    """Return a semantic-version core tuple for a valid release tag."""
    import re

    number = r"(?:0|[1-9]\d*)"
    prerelease_id = rf"(?:{number}|\d*[A-Za-z-][0-9A-Za-z-]*)"
    identifier = r"[0-9A-Za-z-]+"
    match = re.fullmatch(
        rf"v?({number})\.({number})\.({number})"
        rf"(?:-{prerelease_id}(?:\.{prerelease_id})*)?"
        rf"(?:\+{identifier}(?:\.{identifier})*)?",
        version,
    )
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _block_pre_bridge_downgrade(version: str | None) -> None:
    """Reject invalid targets and rollbacks that predate the safe Phase A bridge."""
    if version is None:
        return
    target = _semver_core(version)
    if target is None:
        raise click.ClickException(
            f"Invalid update target {version!r}; expected a semantic version release tag "
            "such as v2.96.1. Branches and Git revision expressions are not allowed."
        )
    prerelease = "-" in version.removeprefix("v").split("+", 1)[0]
    if target < _BRIDGE_BASELINE or (
        target == _BRIDGE_BASELINE and prerelease
    ):
        raise click.ClickException(
            "pkm update cannot roll back below v2.96.1 because older releases do not "
            "contain the safe update bridge. Manual rollback requires stop/quarantine "
            "of PKM services followed by a direct install of the target version."
        )


def _resolve_current_pkm_executable(argv0: str | None = None) -> Path:
    """Resolve the exact current pkm entrypoint before update mutates the install."""
    invocation = sys.argv[0] if argv0 is None else argv0
    invoked_path = Path(invocation).expanduser()
    has_path_component = os.sep in invocation or (
        os.altsep is not None and os.altsep in invocation
    )
    is_direct_pkm = invoked_path.name in {"pkm", "pkm.exe"} and (
        invoked_path.is_absolute() or has_path_component
    )

    if is_direct_pkm:
        candidate = Path(os.path.abspath(invoked_path))
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        raise click.ClickException(
            "The directly invoked current pkm executable does not exist or is not "
            f"executable: {candidate}"
        )

    discovered = shutil.which("pkm")
    if discovered is not None:
        candidate = Path(os.path.abspath(os.path.expanduser(discovered)))
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    raise click.ClickException(
        "Could not resolve the current pkm executable before updating; no files or "
        "repositories were changed. Invoke pkm by its absolute path or restore it on PATH."
    )


def _extra_installed(import_check: str) -> bool:
    """Check whether a Python package is installed without importing it."""
    return find_spec(import_check) is not None


# Map of optional extras → the import that proves they are installed.
_EXTRAS_PROBE: dict[str, str] = {
    "search": "sentence_transformers",
}


def _installed_extras() -> list[str]:
    """Return the list of optional extras currently installed."""
    return [name for name, probe in _EXTRAS_PROBE.items() if _extra_installed(probe)]


def _truthy_config(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _configured_extras() -> list[str]:
    """Return optional extras requested by the saved setup configuration."""
    setup_config = load_config().get("setup", {})
    if not isinstance(setup_config, dict):
        return []

    extras: list[str] = []
    if _truthy_config(setup_config.get("install_search")):
        extras.append("search")
    return extras


def _extras_suffix() -> str:
    """Build the pip extras suffix, e.g. '[search,mcp]' or ''."""
    requested = set(_installed_extras()) | set(_configured_extras())
    extras = [name for name in _EXTRAS_PROBE if name in requested]
    return f"[{','.join(extras)}]" if extras else ""


def _git_stdout(repo_dir: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _current_branch(repo_dir: Path) -> str | None:
    output = _git_stdout(repo_dir, "branch", "--show-current")
    if output is None:
        return None
    branch = output.strip()
    return branch or None


def _main_worktree_cli_dir(repo_dir: Path) -> Path | None:
    output = _git_stdout(repo_dir, "worktree", "list", "--porcelain")
    if output is None:
        return None

    current_worktree: Path | None = None
    for line in [*output.splitlines(), ""]:
        if not line:
            current_worktree = None
            continue
        if line.startswith("worktree "):
            current_worktree = Path(line.removeprefix("worktree "))
            continue
        if line == "branch refs/heads/main" and current_worktree is not None:
            cli_dir = current_worktree / "cli"
            if (cli_dir / "pyproject.toml").exists():
                return cli_dir
    return None


def _select_update_cli_dir(cli_dir: Path, *, dev_current_branch: bool) -> Path:
    if dev_current_branch:
        return cli_dir

    repo_dir = cli_dir.parent
    branch = _current_branch(repo_dir)
    if branch in (None, "main"):
        return cli_dir

    main_cli_dir = _main_worktree_cli_dir(repo_dir)
    if main_cli_dir is not None:
        console.print(
            "[dim]Installed from branch "
            f"'{branch}'. Using main worktree at {main_cli_dir.parent}.[/dim]"
        )
        return main_cli_dir

    raise click.ClickException(
        "pkm update defaults to the main worktree, but this install is running "
        f"from branch '{branch}' and no main worktree was found.\n"
        "Run `pkm update --dev-current-branch` to update this development "
        "worktree, or create/check out a main worktree and retry."
    )


def _run_fresh_post_update(executable: Path, prev_version: str) -> None:
    """Run post-install synchronization through the newly installed CLI process."""
    command = [str(executable), "post-update", "--from-version", prev_version]
    try:
        result = subprocess.run(command)
    except OSError as exc:
        raise click.ClickException(
            f"pkm was reinstalled, but post-update could not start: {exc}"
        ) from exc
    if result.returncode != 0:
        raise click.ClickException(
            "pkm was reinstalled, but post-update failed "
            f"(exit code {result.returncode}). Retry with: {shlex.join(command)}"
        )


_WEB_SERVICE = "pkm-web.service"


def _quiesce_running_web_service() -> bool:
    """Stop an active v2/v3 web service before mutating source or packages."""
    if shutil.which("systemctl") is None:
        return False

    active = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", _WEB_SERVICE],
        capture_output=True,
        text=True,
    )
    if active.returncode != 0:
        return False

    console.print(f"[cyan]Stopping {_WEB_SERVICE} for a safe update...[/cyan]")
    stopped = subprocess.run(
        ["systemctl", "--user", "stop", _WEB_SERVICE],
        capture_output=True,
        text=True,
    )
    if stopped.returncode != 0:
        raise click.ClickException(
            f"Could not stop {_WEB_SERVICE}; no source or package changes were made."
        )

    still_active = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", _WEB_SERVICE],
        capture_output=True,
        text=True,
    )
    if still_active.returncode == 0:
        raise click.ClickException(
            f"{_WEB_SERVICE} is still active; refusing to update while the old runtime can run."
        )
    return True


def _restart_web_service() -> None:
    """Reload, restart, and verify a service that was active before the update."""
    reloaded = subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True,
        text=True,
    )
    if reloaded.returncode != 0:
        raise click.ClickException(
            f"pkm was updated, but systemd could not reload {_WEB_SERVICE}."
        )
    started = subprocess.run(
        ["systemctl", "--user", "start", _WEB_SERVICE],
        capture_output=True,
        text=True,
    )
    if started.returncode != 0:
        raise click.ClickException(
            f"pkm was updated, but {_WEB_SERVICE} could not be restarted."
        )
    active = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", _WEB_SERVICE],
        capture_output=True,
        text=True,
    )
    if active.returncode != 0:
        raise click.ClickException(
            f"pkm was updated, but {_WEB_SERVICE} did not become active."
        )
    console.print(f"[green]✓ {_WEB_SERVICE} restarted.[/green]")


@click.command("update")
@click.argument("version", default=None, required=False)
@click.option(
    "--dev-current-branch",
    is_flag=True,
    help="Development-only: pull/reinstall the currently installed git branch instead of main.",
)
@click.pass_context
def update_cmd(
    ctx: click.Context, version: str | None, dev_current_branch: bool
) -> None:
    """Update pkm to the latest version, or a specific VERSION tag (e.g. v0.3.0)."""
    from pkm import __version__ as prev_version

    _block_pre_bridge_downgrade(version)
    pkm_executable = _resolve_current_pkm_executable()
    service_was_active = _quiesce_running_web_service()
    service_restart_allowed = False
    if service_was_active:

        def finish_service_lifecycle() -> None:
            if service_restart_allowed:
                _restart_web_service()
                return
            console.print(
                f"[yellow]Update did not complete; {_WEB_SERVICE} remains stopped.[/yellow]\n"
                f"After correcting the update failure, retry `pkm update`. To restore the "
                f"previously installed runtime manually, run:\n"
                f"  systemctl --user daemon-reload\n"
                f"  systemctl --user start {_WEB_SERVICE}"
            )

        ctx.call_on_close(finish_service_lifecycle)
    cli_dir = find_local_cli_dir()
    in_git_repo = cli_dir is not None and (cli_dir.parent / ".git").exists()

    if in_git_repo:
        cli_dir = _select_update_cli_dir(
            cli_dir, dev_current_branch=dev_current_branch
        )
        repo_dir = cli_dir.parent  # type: ignore[union-attr]

        if version:
            tag = _normalize_tag(version)
            console.print(f"[cyan]Fetching tags from {repo_dir}...[/cyan]")
            result = subprocess.run(["git", "-C", str(repo_dir), "fetch", "--tags"])
            if result.returncode != 0:
                raise click.ClickException("git fetch failed.")

            console.print(f"[cyan]Checking out {tag}...[/cyan]")
            result = subprocess.run(
                ["git", "-C", str(repo_dir), "checkout", tag],
                capture_output=True,
            )
            if result.returncode != 0:
                console.print(f"[red]✗ Version {tag} not found.[/red]")
                versions = get_recent_versions(5)
                if not versions:
                    local = subprocess.run(
                        ["git", "-C", str(repo_dir), "tag", "--sort=-version:refname"],
                        capture_output=True,
                        text=True,
                    )
                    versions = [
                        t for t in local.stdout.splitlines() if t.startswith("v")
                    ][:5]
                if versions:
                    console.print("[yellow]Available versions:[/yellow]")
                    for v in versions:
                        console.print(f"  {v}")
                else:
                    console.print("[yellow]No tagged releases found yet.[/yellow]")
                raise click.ClickException(f"Could not checkout {tag}.")
        else:
            console.print(f"[cyan]Pulling latest from {repo_dir}...[/cyan]")
            result = subprocess.run(["git", "-C", str(repo_dir), "pull", "--ff-only"])
            if result.returncode != 0:
                raise click.ClickException(
                    "git pull --ff-only failed. Your local branch has diverged from remote.\n"
                    "To resolve, run one of:\n"
                    "  git -C {repo_dir} pull --rebase   # rebase local commits on top of remote\n"
                    "  git -C {repo_dir} reset --hard origin/main  # discard local changes".format(
                        repo_dir=repo_dir
                    )
                )

        console.print("[cyan]Reinstalling...[/cyan]")
        suffix = _extras_suffix()
        if suffix:
            console.print(f"[dim]Extras detected: {suffix}[/dim]")
        install_target = str(cli_dir) + suffix
        result = subprocess.run(
            [
                "uv",
                "tool",
                "install",
                "--editable",
                install_target,
                "--reinstall-package",
                "pkm",
            ],
        )
        if result.returncode != 0:
            raise click.ClickException("uv tool install failed.")

    else:
        # Installed without a local git repo (e.g. via curl | bash).
        # Re-download the requested release tag or latest main tarball and reinstall.
        tag = _normalize_tag(version) if version else None
        label = tag or "latest"
        console.print(f"[cyan]Downloading {label} from GitHub...[/cyan]")
        try:
            with cli_source(ref=tag) as (dl_cli_dir, is_local):
                suffix = _extras_suffix()
                if suffix:
                    console.print(f"[dim]Extras detected: {suffix}[/dim]")
                install_target = str(dl_cli_dir) + suffix
                console.print("[cyan]Reinstalling...[/cyan]")
                result = subprocess.run(
                    [
                        "uv",
                        "tool",
                        "install",
                        install_target,
                        "--reinstall-package",
                        "pkm",
                    ],
                )
                if result.returncode != 0:
                    raise click.ClickException("uv tool install failed.")
        except (RuntimeError, OSError) as e:
            raise click.ClickException(str(e))

    _run_fresh_post_update(pkm_executable, prev_version)

    try:
        if in_git_repo:
            import re

            changelog_path = repo_dir / "CHANGELOG.md"
            if changelog_path.exists():
                content = changelog_path.read_text(encoding="utf-8")
                sections = re.split(r"\n## (v[0-9]+\.[0-9]+\.[0-9]+.*)\n", content)
                if len(sections) >= 3:
                    parsed = []
                    for i in range(1, len(sections), 2):
                        header = "## " + sections[i]
                        body = sections[i + 1].strip()
                        parsed.append((header, body))

                    since_v = (
                        prev_version
                        if prev_version.startswith("v")
                        else f"v{prev_version}"
                    )
                    idx = -1
                    for i, (h, b) in enumerate(parsed):
                        if since_v in h:
                            idx = i
                            break

                    if idx > 0:
                        cl_text = "\n\n".join(f"{h}\n\n{b}" for h, b in parsed[:idx])
                        from rich.markdown import Markdown

                        console.print(f"\n[bold]Changes since {since_v}:[/bold]")
                        console.print(Markdown(cl_text))
                    elif idx == 0:
                        console.print(
                            f"\n[dim]No new changes found in changelog since {since_v}.[/dim]"
                        )
    except Exception:
        pass

    result = subprocess.run(
        [str(pkm_executable), "--version"], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise click.ClickException(
            "pkm was reinstalled, but the new executable failed its version check."
        )

    first_line = result.stdout.strip().split("\n")[0]
    if version:
        expected_tag = _normalize_tag(version)
        if not first_line.startswith(f"pkm {expected_tag}"):
            raise click.ClickException(
                f"pkm was reinstalled, but expected {expected_tag} and found: "
                f"{first_line or '(empty version output)'}"
            )

    console.print("[green]✓ pkm updated.[/green]")
    console.print(f"\n[bold green]Now running: {first_line}[/bold green]")
    service_restart_allowed = True
