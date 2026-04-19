import json
import os
from pathlib import Path

from tiny_agent.tools import tool

from pkm.config import VaultConfig


def _get_vault(vault_dir: str) -> VaultConfig:
    return VaultConfig(name=Path(vault_dir).name, path=Path(vault_dir))


@tool()
def find_backlinks_for_note(note_id: str) -> str:
    """Find all notes that link TO a given note (inbound wikilinks). Daemon-free.

    Use when the user asks what references a note, who cites it, or to explore
    connections to a hub note. Prefer get_graph_context when depth>1 or outbound
    links are needed; use this tool when the daemon is unavailable or only inbound
    links are needed. Returns JSON: {note_id, backlinks: [{title, path, note_id}], count}.
    """
    try:
        vault = _get_vault(os.environ.get("PKM_VAULT_DIR", "."))
        from pkm.wikilinks import find_backlinks
        from pkm.frontmatter import parse

        paths = find_backlinks(vault, note_id)
        items = []
        for p in paths:
            try:
                note = parse(p)
                items.append({"title": note.title, "path": p.name, "note_id": p.stem})
            except Exception:
                items.append({"title": p.stem, "path": p.name, "note_id": p.stem})
        return json.dumps(
            {"note_id": note_id, "backlinks": items, "count": len(items)}, indent=2
        )
    except Exception as e:
        return f"Error: {e}"
