import json
import os
from pathlib import Path

from tiny_agent.tools import tool

from pkm.config import VaultConfig


def _get_vault(vault_dir: str) -> VaultConfig:
    return VaultConfig(name=Path(vault_dir).name, path=Path(vault_dir))


@tool()
def vault_stats() -> str:
    """Get a snapshot of vault health: note count, orphan count, tag count, avg links, index status.

    Use when the user asks about vault size, health check, or needs to decide whether to
    run a maintenance workflow. Returns JSON with keys: notes, dailies, tasks, orphans,
    unique_tags, avg_links_per_note, index.
    """
    vault = _get_vault(os.environ.get("PKM_VAULT_DIR", "."))
    try:
        from pkm.commands.maintenance import compute_vault_stats

        result = compute_vault_stats(vault)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"


@tool()
def list_stale_notes(days: int = 30) -> str:
    """List notes not modified in the last N days (default 30), oldest first.

    Use when the user wants to find neglected notes, candidates for pruning, or
    asks what they haven't touched recently. Returns JSON with keys:
    threshold_days, stale_notes (list of {note, last_modified, days_ago}), count.
    """
    vault = _get_vault(os.environ.get("PKM_VAULT_DIR", "."))
    try:
        from pkm.commands.maintenance import list_stale

        result = list_stale(vault, days)
        return json.dumps(
            {"threshold_days": days, "stale_notes": result, "count": len(result)},
            indent=2,
        )
    except Exception as e:
        return f"Error: {e}"


@tool()
def list_orphans() -> str:
    """List all orphan notes — notes with zero inbound AND zero outbound wikilinks.

    Use when the user wants to find disconnected knowledge, candidates for linking,
    or asks which notes are not connected to anything. Returns JSON with keys:
    orphans (list of {filename, note_id, tags}), count.
    """
    vault = _get_vault(os.environ.get("PKM_VAULT_DIR", "."))
    try:
        from pkm.frontmatter import parse
        from pkm.wikilinks import find_orphans

        orphan_paths = find_orphans(vault)
        items = []
        for path in orphan_paths:
            note = parse(path)
            items.append(
                {
                    "filename": path.name,
                    "note_id": path.stem,
                    "tags": note.tags,
                }
            )
        return json.dumps({"orphans": items, "count": len(items)}, indent=2)
    except Exception as e:
        return f"Error: {e}"
