"""Interactive setup wizard for pkm."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click
from rich.console import Console

from pkm.commands.vault import init_vault_dirs
from pkm.config import CONFIG_PATH, discover_vaults, load_config

console = Console()


def _sync_dir(src: Path, dst: Path) -> None:
    """Sync src into dst: remove files/dirs in dst not present in src, then copy all from src."""
    dst.mkdir(parents=True, exist_ok=True)
    src_names = {p.name for p in src.iterdir()}
    for existing in list(dst.iterdir()):
        if existing.name not in src_names:
            if existing.is_dir():
                shutil.rmtree(existing)
            else:
                existing.unlink()
    shutil.copytree(str(src), str(dst), dirs_exist_ok=True)


def _find_skill_src() -> Path | None:
    """Locate the plugin/skills/pkm/ directory from the repo root."""
    from pkm._install_source import find_local_cli_dir

    cli_dir = find_local_cli_dir()
    if cli_dir is not None:
        candidate = cli_dir.parent / "plugin" / "skills" / "pkm"
        if candidate.is_dir():
            return candidate
    return None


def install_skill_files() -> bool:
    """Install/sync skill and command files to ~/.claude and ~/.agents. Returns True if found."""
    skill_src = _find_skill_src()
    if skill_src is None:
        return False

    for dest, label in [
        (Path.home() / ".claude" / "skills" / "pkm", "~/.claude/skills/pkm/"),
        (Path.home() / ".agents" / "skills" / "pkm", "~/.agents/skills/pkm/"),
    ]:
        _sync_dir(skill_src, dest)
        console.print(f"[green]✓ PKM skill synced ({label})[/green]")

    commands_src = skill_src / "commands" / "pkm"
    if commands_src.is_dir():
        for dest, label in [
            (Path.home() / ".claude" / "commands" / "pkm", "~/.claude/commands/pkm/"),
            (Path.home() / ".agents" / "commands" / "pkm", "~/.agents/commands/pkm/"),
        ]:
            _sync_dir(commands_src, dest)
            console.print(f"[green]✓ PKM commands synced ({label})[/green]")

    return True


def install_shell_aliases() -> None:
    """Add pkmcd alias to ~/.bashrc and ~/.zshrc if they exist."""
    alias_line = "alias pkmcd='cd $(pkm vault where)'"
    for shell_rc in [Path.home() / ".bashrc", Path.home() / ".zshrc"]:
        if shell_rc.exists():
            content = shell_rc.read_text(encoding="utf-8")
            if "alias pkmcd=" not in content:
                with shell_rc.open("a", encoding="utf-8") as f:
                    f.write(f"\n{alias_line}\n")
                console.print(f"[green]✓ Added pkmcd alias to {shell_rc.name}[/green]")


def _load_setup_choices() -> dict | None:
    """Return saved setup choices from config, or None if not previously saved."""
    cfg = load_config()
    s = cfg.get("setup", {})
    required = {"install_search", "install_dev", "vaults_root", "default_vault"}
    return s if required.issubset(s.keys()) else None


def _save_config_merged(setup_choices: dict, default_vault: str) -> None:
    """Merge setup choices + defaults into ~/.config/pkm/config (preserves other sections)."""
    cfg = load_config()
    cfg["setup"] = setup_choices
    cfg.setdefault("defaults", {})["vault"] = default_vault
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for section, values in cfg.items():
        lines.append(f"[{section}]")
        for k, v in values.items():
            if isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            else:
                lines.append(f'{k} = "{v}"')
        lines.append("")
    CONFIG_PATH.write_text("\n".join(lines), encoding="utf-8")


@click.command("setup")
def setup_cmd() -> None:
    """Interactive setup wizard: install dependencies, configure vaults."""
    console.print("[bold]PKM Setup Wizard[/bold]")
    console.print()

    # Check for previously saved setup choices
    saved = _load_setup_choices()
    use_saved = False
    if saved:
        console.print("[cyan]Previous configuration found:[/cyan]")
        console.print(
            f"  search features: {'Yes' if saved['install_search'] == 'true' or saved['install_search'] is True else 'No'}"
        )
        console.print(
            f"  dev tools:       {'Yes' if saved['install_dev'] == 'true' or saved['install_dev'] is True else 'No'}"
        )
        console.print(f"  vault root:      {saved['vaults_root']}")
        console.print(f"  default vault:   {saved['default_vault']}")
        console.print()
        use_saved = click.confirm("Keep existing configuration?", default=True)
        console.print()

    if use_saved and saved:
        # Quick path: reuse saved choices
        install_search = saved["install_search"] in (True, "true")
        install_dev = saved["install_dev"] in (True, "true")
        vaults_root = Path(saved["vaults_root"]).expanduser()
        default_vault = saved["default_vault"]
    else:
        # Full interactive setup
        install_search = click.confirm(
            "Install search features? (sentence-transformers ~500MB, enables 'pkm search')",
            default=True,
        )
        install_dev = click.confirm(
            "Install dev tools? (pytest, for running tests)",
            default=False,
        )

        default_root = str(Path.home() / "vaults")
        vaults_root_str = click.prompt("Vault root directory", default=default_root)
        vaults_root = Path(vaults_root_str).expanduser()

        existing = discover_vaults(vaults_root)
        if existing:
            vault_names = ", ".join(existing.keys())
            console.print(f"[cyan]ℹ Found existing vaults:[/cyan] {vault_names}")
            first_name = next(iter(existing))
            default_vault = click.prompt("Default vault", default=first_name)
            if default_vault not in existing:
                console.print(
                    f"[yellow]Warning:[/yellow] '{default_vault}' not found in {vaults_root}. "
                    "Creating it..."
                )
                vault_path = vaults_root / default_vault
                init_vault_dirs(vault_path, default_vault)
                console.print(f"[green]✓ Created vault '{default_vault}'[/green]")
        else:
            console.print(f"No vaults found under {vaults_root}.")
            vault_name = click.prompt("New vault name")
            if not vault_name or "/" in vault_name or "\\" in vault_name:
                raise click.ClickException(
                    f"Invalid vault name '{vault_name}': must be non-empty and contain no slashes."
                )
            vault_path = vaults_root / vault_name
            init_vault_dirs(vault_path, vault_name)
            console.print(
                f"[green]✓ Created vault '{vault_name}'[/green] at {vault_path}"
            )
            default_vault = vault_name

    # Install selected extras
    extras: list[str] = []
    if install_search:
        extras.append("search")
    if install_dev:
        extras.append("dev")

    console.print(
        f"Installing pkm{('[' + ','.join(extras) + ']') if extras else ''}..."
    )

    try:
        from pkm._install_source import cli_source

        with cli_source() as (cli_dir, is_local):
            extra_spec = str(cli_dir) + (f"[{','.join(extras)}]" if extras else "")
            flags = ["--editable"] if is_local else []
            if not is_local:
                console.print("[cyan]Downloading latest source from GitHub...[/cyan]")
            result = subprocess.run(
                [
                    "uv",
                    "tool",
                    "install",
                    *flags,
                    extra_spec,
                    "--reinstall-package",
                    "pkm",
                ],
            )
            if result.returncode != 0:
                raise click.ClickException(
                    "Dependency installation failed. Check uv output above."
                )
    except RuntimeError as e:
        raise click.ClickException(str(e))

    console.print("[green]✓ Dependencies installed[/green]")
    console.print()

    # Save config (setup choices + default vault), merging with any existing sections
    _save_config_merged(
        setup_choices={
            "install_search": install_search,
            "install_dev": install_dev,
            "vaults_root": str(vaults_root),
            "default_vault": default_vault,
        },
        default_vault=default_vault,
    )
    console.print(f"[green]✓ Default vault set to '{default_vault}'[/green]")

    # Sync skill and command files (removes stale, copies current)
    if not install_skill_files():
        console.print(
            "[yellow]⚠ Skill files not found in package — skipping skill install[/yellow]"
        )

    install_shell_aliases()

    # Done
    console.print()
    console.print("[bold green]✓ Setup complete![/bold green]")
    console.print()
    console.print("Try these commands to get started:")
    console.print("  [bold]pkm daily[/bold]       — show/create today's daily note")
    console.print("  [bold]pkm note add[/bold] 'Title'  — create a new atomic note")
    if install_search:
        console.print("  [bold]pkm index[/bold]       — build search index")
        console.print("  [bold]pkm search[/bold] '...' — semantic search")
    console.print()
    console.print("Claude Code slash commands (after restarting Claude Code):")
    console.print("  [bold]/pkm:init-daily[/bold]        — start today's note")
    console.print(
        "  [bold]/pkm:distill-daily[/bold]     — promote daily → atomic notes"
    )
    console.print(
        "  [bold]/pkm:dream[/bold]             — nightly knowledge consolidation"
    )
    console.print("  [bold]/pkm:weekly-review[/bold]     — weekly synthesis")
    console.print("  [bold]/pkm:auto-tagging[/bold]      — tag untagged notes")
