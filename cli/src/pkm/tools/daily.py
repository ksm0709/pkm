import os
from pathlib import Path
from datetime import datetime
from tiny_agent.agent import tool
from pkm.config import VaultConfig
from pkm.commands.daily import add_daily_entry


def _get_vault(vault_dir: str) -> VaultConfig:
    return VaultConfig(name=Path(vault_dir).name, path=Path(vault_dir))


@tool
def add_daily_log(text: str, vault_dir: str | None = None) -> str:
    """Append a timestamped log entry to today's daily note.

    Args:
        text: The text to log.
        vault_dir: The vault directory path. If not provided, uses PKM_VAULT_DIR env var.
    """
    v_dir = vault_dir or os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)

    try:
        entry = add_daily_entry(vault, text)
        return f"Successfully added daily log: {entry.strip()}"
    except Exception as e:
        return f"Error adding daily log: {str(e)}"


@tool
def read_daily_log(date_str: str | None = None, vault_dir: str | None = None) -> str:
    """Read the daily note for a specific date.

    Args:
        date_str: The date in YYYY-MM-DD format. Defaults to today.
        vault_dir: The vault directory path. If not provided, uses PKM_VAULT_DIR env var.
    """
    v_dir = vault_dir or os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)

    target_date = date_str or datetime.now().strftime("%Y-%m-%d")
    note_path = vault.daily_dir / f"{target_date}.md"

    if not note_path.exists():
        return f"No daily note found for {target_date}"

    try:
        return note_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading daily note: {str(e)}"
