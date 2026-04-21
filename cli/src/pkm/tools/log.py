import os
from pathlib import Path

from tiny_agent.tools import tool
from pkm.config import VaultConfig


def _get_vault(vault_dir: str) -> VaultConfig:
    path = Path(vault_dir)
    return VaultConfig(name=path.name, path=path)


@tool()
def read_recent_note_activity(tail: int = 20) -> str:
    """Read the last N entries from the note operation log (.pkm/log.md). Best-effort only.

    Use when the user asks about recent note changes, what was modified in a previous
    session, or to audit agent actions. Note: the log writer silently swallows errors,
    so this log may be incomplete. Returns last N non-empty lines as plain text.
    """
    try:
        vault = _get_vault(os.environ.get("PKM_VAULT_DIR", "."))
        log_path = vault.pkm_dir / "log.md"
        if not log_path.exists():
            return "No activity log yet."
        lines = log_path.read_text(encoding="utf-8").splitlines()
        non_empty = [line for line in lines if line.strip()]
        return "\n".join(non_empty[-tail:])
    except Exception as e:
        return f"Error: {e}"
