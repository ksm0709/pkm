"""Interactive setup wizard for pkm."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click
from rich.console import Console

from pkm.commands.vault import init_vault_dirs
from pkm.config import discover_vaults, save_config

console = Console()


@click.command("setup")
def setup_cmd() -> None:
    """Interactive setup wizard: install dependencies, configure vaults."""
    console.print("[bold]PKM Setup Wizard[/bold]")
    console.print()

    # Step 1: Feature selection
    install_search = click.confirm(
        "Install search features? (sentence-transformers ~500MB, enables 'pkm search')",
        default=True,
    )
    install_dev = click.confirm(
        "Install dev tools? (pytest, for running tests)",
        default=False,
    )

    # Step 2: Install selected extras
    extras: list[str] = []
    if install_search:
        extras.append("search")
    if install_dev:
        extras.append("dev")

    console.print()
    console.print(f"Installing pkm{('[' + ','.join(extras) + ']') if extras else ''}...")

    try:
        from pkm._install_source import cli_source
        with cli_source() as (cli_dir, is_local):
            extra_spec = str(cli_dir) + (f"[{','.join(extras)}]" if extras else "")
            flags = ["--editable"] if is_local else []
            if not is_local:
                console.print("[cyan]Downloading latest source from GitHub...[/cyan]")
            result = subprocess.run(
                ["uv", "tool", "install", *flags, extra_spec, "--reinstall-package", "pkm"],
            )
            if result.returncode != 0:
                raise click.ClickException("Dependency installation failed. Check uv output above.")
    except RuntimeError as e:
        raise click.ClickException(str(e))

    console.print("[green]✓ Dependencies installed[/green]")
    console.print()

    # Step 3: Vault root
    default_root = str(Path.home() / "vaults")
    vaults_root_str = click.prompt("Vault root directory", default=default_root)
    vaults_root = Path(vaults_root_str).expanduser()

    # Step 4: Detect existing vaults
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
        console.print(f"[green]✓ Created vault '{vault_name}'[/green] at {vault_path}")
        default_vault = vault_name

    # Step 5: Save config
    save_config({"defaults": {"vault": default_vault}})
    console.print(f"[green]✓ Default vault set to '{default_vault}'[/green]")

    # Step 6: Install skill files to ~/.claude/skills/pkm/
    skill_src = Path(__file__).parent.parent / "skill"
    if skill_src.is_dir():
        skill_dest_claude = Path.home() / ".claude" / "skills" / "pkm"
        shutil.copytree(str(skill_src), str(skill_dest_claude), dirs_exist_ok=True)
        console.print("[green]✓ PKM skill installed to ~/.claude/skills/pkm/[/green]")

        skill_dest_agents = Path.home() / ".agents" / "skills" / "pkm"
        shutil.copytree(str(skill_src), str(skill_dest_agents), dirs_exist_ok=True)
        console.print("[green]✓ PKM skill installed to ~/.agents/skills/pkm/[/green]")
    else:
        console.print("[yellow]⚠ Skill files not found in package — skipping skill install[/yellow]")

    # Step 7: Done
    console.print()
    console.print("[bold green]✓ Setup complete![/bold green]")
    console.print()
    console.print("Try these commands to get started:")
    console.print("  [bold]pkm daily[/bold]       — show/create today's daily note")
    console.print("  [bold]pkm note add[/bold] 'Title'  — create a new atomic note")
    if install_search:
        console.print("  [bold]pkm index[/bold]       — build search index")
        console.print("  [bold]pkm search[/bold] '...' — semantic search")
