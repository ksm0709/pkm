"""MCP server exposing PKM vault tools for AI agents.

Runs as a foreground stdio server. An MCP client spawns this process via config:
    command = "pkm"
    args = ["mcp", "--vault", "my-vault"]
"""

from __future__ import annotations

from pathlib import Path

import click
from mcp.server.fastmcp import FastMCP

from pkm.config import VaultConfig, get_vault

mcp = FastMCP("pkm")

_current_vault: VaultConfig | None = None


def _get_vault(vault_name: str | None = None) -> VaultConfig:
    """Resolve vault — use override name or fall back to server default."""
    if vault_name:
        try:
            return get_vault(vault_name)
        except click.ClickException as e:
            raise ValueError(str(e.message))
    if _current_vault is None:
        raise ValueError("No vault configured for MCP server")
    return _current_vault


@mcp.tool()
def note_add(
    content: str,
    title: str | None = None,
    type: str | None = None,
    importance: int | None = None,
    tags: list[str] | None = None,
    meta: dict | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
) -> dict:
    """Create an atomic note in the PKM vault.

    Args:
        content: Note body text (required).
        title: Note title. Auto-generated from content if omitted.
        type: Memory type — semantic, episodic, or procedural.
        importance: Importance score 1-10 (default 5).
        tags: List of tags.
        meta: Arbitrary key-value metadata added to frontmatter.
        session_id: Session tracking ID.
        agent_id: Agent tracking ID.
    """
    from pkm.commands.notes import create_note

    vault = _get_vault()
    try:
        note_path = create_note(
            vault=vault,
            title=title,
            content=content,
            memory_type=type,
            importance=importance,
            session_id=session_id,
            agent_id=agent_id,
            tags=tags,
            meta=meta,
        )
        return {"status": "created", "path": str(note_path), "note_id": note_path.stem}
    except (ValueError, FileExistsError) as e:
        return {"error": str(e)}
    except click.ClickException as e:
        return {"error": str(e.message)}


@mcp.tool()
def daily_add(text: str) -> dict:
    """Append a timestamped log entry to today's daily note.

    Args:
        text: The text to add to today's daily note.
    """
    from pkm.commands.daily import add_daily_entry

    vault = _get_vault()
    try:
        entry = add_daily_entry(vault, text)
        return {"status": "added", "entry": entry.strip()}
    except click.ClickException as e:
        return {"error": str(e.message)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def search(
    query: str,
    top: int = 10,
    vault: str | None = None,
    memory_type: str | None = None,
    min_importance: float = 1.0,
) -> dict:
    """Search notes semantically via the PKM daemon.

    Args:
        query: Search query string.
        top: Maximum number of results (default 10).
        vault: Vault name for cross-vault search. Uses server vault if omitted.
        memory_type: Filter by type — semantic, episodic, or procedural.
        min_importance: Minimum importance score filter (default 1.0).
    """
    from pkm.search_engine import search_via_daemon

    target_vault = _get_vault(vault)
    try:
        results = search_via_daemon(
            query,
            target_vault,
            top_n=top,
            memory_type_filter=memory_type,
            min_importance=min_importance,
        )
        if results is None:
            return {"error": "Daemon unavailable. Start with: pkm daemon start", "code": -32000}
        return {
            "results": [
                {
                    "note_id": r.note_id,
                    "title": r.title,
                    "score": round(r.score, 4),
                    "tags": r.tags,
                    "memory_type": r.memory_type,
                    "importance": r.importance,
                    "path": r.path,
                    "rank": r.rank,
                }
                for r in results
            ],
            "count": len(results),
        }
    except click.ClickException as e:
        return {"error": str(e.message)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def index() -> dict:
    """Rebuild the semantic search index for the current vault."""
    from pkm.search_engine import build_index

    vault = _get_vault()
    try:
        result = build_index(vault)
        return {"status": "indexed", "count": len(result.entries)}
    except click.ClickException as e:
        return {"error": str(e.message)}
    except Exception as e:
        return {"error": str(e)}


def run_server(vault: VaultConfig) -> None:
    """Start the MCP stdio server bound to the given vault."""
    global _current_vault
    _current_vault = vault
    mcp.run(transport="stdio")
