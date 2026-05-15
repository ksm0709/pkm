"""pkm update — pull latest or a specific version and reinstall."""

from __future__ import annotations

import subprocess
from importlib.util import find_spec
from pathlib import Path

import click
from rich.console import Console

from pkm._install_source import cli_source, find_local_cli_dir
from pkm.commands.setup import (
    install_shell_aliases,
    install_skill_files,
    sync_existing_web_unit,
)
from pkm.config import load_config
from pkm.version_check import get_recent_versions
from pkm.workflows import sync_installed_workflow_defaults

console = Console()


def _normalize_tag(version: str) -> str:
    """Ensure version has a 'v' prefix (e.g. '0.3.0' → 'v0.3.0')."""
    return version if version.startswith("v") else f"v{version}"


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


@click.command("update")
@click.argument("version", default=None, required=False)
@click.option(
    "--dev-current-branch",
    is_flag=True,
    help="Development-only: pull/reinstall the currently installed git branch instead of main.",
)
def update_cmd(version: str | None, dev_current_branch: bool) -> None:
    """Update pkm to the latest version, or a specific VERSION tag (e.g. v0.3.0)."""
    from pkm import __version__ as prev_version

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
        if version:
            raise click.ClickException(
                "Specific version installs require a local git checkout. "
                "Clone the repo: git clone https://github.com/ksm0709/pkm ~/repos/pkm"
            )
        # Installed without a local git repo (e.g. via curl | bash).
        # Re-download the latest tarball from GitHub and reinstall.
        console.print("[cyan]Downloading latest from GitHub...[/cyan]")
        try:
            with cli_source() as (dl_cli_dir, is_local):
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
        except RuntimeError as e:
            raise click.ClickException(str(e))

    console.print("[green]✓ pkm updated.[/green]")

    # Sync skill and command files — removes stale commands from old versions
    install_skill_files()
    install_shell_aliases()
    unit_path = sync_existing_web_unit()
    if unit_path is not None:
        console.print(f"[green]✓ PKM web unit synced:[/green] {unit_path}")
    workflow_path = sync_installed_workflow_defaults()
    if workflow_path is not None:
        console.print(f"[green]✓ PKM workflow settings synced:[/green] {workflow_path}")

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

    result = subprocess.run(["pkm", "--version"], capture_output=True, text=True)
    if result.returncode == 0:
        first_line = result.stdout.strip().split("\n")[0]
        console.print(f"\n[bold green]Now running: {first_line}[/bold green]")
