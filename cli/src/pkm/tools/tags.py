import json
import os
from pathlib import Path

from tiny_agent.tools import tool

from pkm.config import VaultConfig


def _get_vault(vault_dir: str) -> VaultConfig:
    return VaultConfig(name=Path(vault_dir).name, path=Path(vault_dir))


@tool()
def list_tags() -> str:
    """List all tags used in the vault with their note counts, sorted by frequency.

    Use when the user asks what tags exist, which topics appear most, or needs to
    discover tag names before calling tag_search. Returns JSON: {tags: [{tag, count}], count}.
    """
    try:
        vault = _get_vault(os.environ.get("PKM_VAULT_DIR", "."))
        from pkm.commands.tag_commands import count_all_tags

        pairs = count_all_tags(vault)
        items = [{"tag": tag, "count": count} for tag, count in pairs]
        return json.dumps({"tags": items, "count": len(items)}, indent=2)
    except Exception as e:
        return f"Error: {e}"


@tool()
def tag_search(pattern: str) -> str:
    """Find notes by tag pattern: exact, glob (db*), AND (python+testing), OR (python,rust).

    Use when filtering notes by topic category — NOT for content queries (use
    search_notes for title match or semantic_search for meaning). Supports:
    exact tag name, glob patterns (*/?), AND with +, OR with comma.
    Returns JSON: {pattern, mode, results: [{title, tags, path}], count}.
    """
    try:
        vault = _get_vault(os.environ.get("PKM_VAULT_DIR", "."))
        from pkm.commands.tag_commands import search_by_tag_pattern

        mode, matched = search_by_tag_pattern(vault, pattern)
        items = [
            {"title": n.title, "tags": n.tags, "path": n.path.name} for n in matched
        ]
        return json.dumps(
            {"pattern": pattern, "mode": mode, "results": items, "count": len(items)},
            indent=2,
        )
    except Exception as e:
        return f"Error: {e}"
