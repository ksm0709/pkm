"""MCP server exposing PKM vault tools for AI agents.

Runs as a foreground stdio server. An MCP client spawns this process via config:
    command = "pkm"
    args = ["mcp", "--vault", "my-vault"]
"""

from __future__ import annotations


from typing import Any

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
    meta: dict[str, Any] | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
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
def daily_add(text: str) -> dict[str, Any]:
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
) -> dict[str, Any]:
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
            return {
                "error": "Daemon unavailable. Start with: pkm daemon start",
                "code": -32000,
            }
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
def index() -> dict[str, Any]:
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


@mcp.tool()
async def pkm_ask(
    query: str,
    vault: str | None = None,
    model: str | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    """Ask a natural language question about your vault.

    Args:
        query: The natural language question to ask.
        vault: Vault name for cross-vault search. Uses server vault if omitted.
        model: Optional LLM model to use. Overrides config if provided.
        timeout: Timeout in seconds to wait for the result.
    """
    import json
    import asyncio
    import os
    from pathlib import Path
    from pkm.config import load_config

    target_vault = _get_vault(vault)
    sock_path = Path.home() / ".config" / "pkm" / "daemon.sock"

    config_model = load_config().get("defaults", {}).get("model")
    final_model = model or config_model or "auto"
    graph_depth = load_config().get("defaults", {}).get("graph-depth", 0)

    env_keys = {k: v for k, v in os.environ.items() if k.endswith("_API_KEY")}

    reader = None
    writer = None
    for attempt in range(50):
        try:
            reader, writer = await asyncio.open_unix_connection(str(sock_path))
            break
        except (FileNotFoundError, ConnectionRefusedError):
            if attempt == 0:
                import subprocess
                import sys

                daemon_dir = Path.home() / ".config" / "pkm"
                daemon_dir.mkdir(parents=True, exist_ok=True)
                try:
                    subprocess.Popen(
                        [sys.executable, "-m", "pkm.daemon"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                except Exception:
                    pass
            await asyncio.sleep(0.1)

    if not writer:
        return {"error": "Daemon failed to start. Run 'pkm daemon start' manually."}

    try:
        req = {
            "action": "ask",
            "query": query,
            "vault_name": target_vault.name,
            "model": final_model,
            "env_keys": env_keys,
            "graph_depth": graph_depth,
        }
        writer.write(json.dumps(req).encode("utf-8") + b"\n")
        await writer.drain()

        data = await asyncio.wait_for(reader.readline(), timeout=timeout)

        if not data:
            return {"error": "No response from daemon."}

        resp = json.loads(data.decode("utf-8"))

        if resp.get("type") == "error" or "error" in resp:
            error_msg = resp.get("message") or resp.get("error", "Unknown error")
            return {"error": error_msg}

        if "data" in resp and "response" in resp["data"]:
            return {"result": resp["data"]["response"]}
        elif "response" in resp:
            return {"result": resp["response"]}
        else:
            return {"error": "Invalid response format from daemon."}

    except asyncio.TimeoutError:
        return {"error": f"Request timed out after {timeout} seconds."}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {e}"}
    finally:
        try:
            if writer:
                writer.close()
                await writer.wait_closed()
        except Exception:
            pass


@mcp.tool()
def vault_stats() -> dict[str, Any]:
    """Get a snapshot of vault health: note count, orphan count, tag count, avg links, index status."""
    from pkm.commands.maintenance import compute_vault_stats

    vault = _get_vault()
    try:
        return compute_vault_stats(vault)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def list_stale_notes(days: int = 30) -> dict[str, Any]:
    """List notes not modified in the last N days (default 30), oldest first."""
    from pkm.commands.maintenance import list_stale

    vault = _get_vault()
    try:
        items = list_stale(vault, days)
        return {"threshold_days": days, "stale_notes": items, "count": len(items)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def list_orphans() -> dict[str, Any]:
    """List all orphan notes — notes with zero inbound AND zero outbound wikilinks."""
    from pkm.wikilinks import find_orphans
    from pkm.frontmatter import parse

    vault = _get_vault()
    try:
        paths = find_orphans(vault)
        items = []
        for p in paths:
            tags = []
            try:
                tags = parse(p).tags
            except Exception:
                pass
            items.append({"filename": p.name, "note_id": p.stem, "tags": tags})
        return {"orphans": items, "count": len(items)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def find_backlinks_for_note(note_id: str) -> dict[str, Any]:
    """Find all notes that link TO a given note (inbound wikilinks). Daemon-free."""
    from pkm.wikilinks import find_backlinks
    from pkm.frontmatter import parse

    vault = _get_vault()
    try:
        paths = find_backlinks(vault, note_id)
        items = []
        for p in paths:
            title = p.stem
            try:
                title = parse(p).title
            except Exception:
                pass
            items.append({"title": title, "path": p.name, "note_id": p.stem})
        return {"note_id": note_id, "backlinks": items, "count": len(items)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_note_neighbors(note_id: str, include_semantic: bool = False) -> dict[str, Any]:
    """Get all neighbors of a note: outbound wikilinks, inbound backlinks, tags, ghost
    nodes, and optionally semantic connections. Daemon-free (reads graph.json directly).

    Returns {note_id, outbound:[{note_id,title,type}], inbound:[{note_id,title,type}],
    semantic:[{note_id,title,type,confidence}]}. All node types included (note, tag,
    note_or_unresolved). Filter by 'type' field as needed.
    Requires pkm index to have been run to build graph.json.
    """
    from pkm.tools.links import _get_note_neighbors_data

    vault = _get_vault()
    try:
        return _get_note_neighbors_data(vault, note_id, include_semantic)
    except FileNotFoundError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def list_tags() -> dict[str, Any]:
    """List all tags used in the vault with their note counts, sorted by frequency."""
    from pkm.commands.tag_commands import count_all_tags

    vault = _get_vault()
    try:
        pairs = count_all_tags(vault)
        items = [{"tag": tag, "count": count} for tag, count in pairs]
        return {"tags": items, "count": len(items)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def tag_search(pattern: str) -> dict[str, Any]:
    """Find notes by tag pattern: exact, glob (db*), AND (python+testing), OR (python,rust)."""
    from pkm.commands.tag_commands import search_by_tag_pattern

    vault = _get_vault()
    try:
        mode, matched = search_by_tag_pattern(vault, pattern)
        items = [
            {"title": n.title, "tags": n.tags, "path": n.path.name} for n in matched
        ]
        return {"pattern": pattern, "mode": mode, "results": items, "count": len(items)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def list_consolidation_candidates() -> dict[str, Any]:
    """List daily notes eligible for Zettelkasten consolidation (not today, not already consolidated)."""
    from pkm.commands.consolidate import _list_candidate_dates

    vault = _get_vault()
    try:
        dates = _list_candidate_dates(vault)
        items = []
        for date_str in dates:
            md_file = vault.daily_dir / f"{date_str}.md"
            entry_count = 0
            try:
                text = md_file.read_text(encoding="utf-8")
                body_start = text.find("---", 3)
                body = text[body_start + 3 :] if body_start != -1 else text
                entry_count = sum(
                    1
                    for line in body.splitlines()
                    if line.strip().startswith(("-", "*", "["))
                )
            except Exception:
                pass
            items.append({"date": date_str, "entry_count": entry_count})
        return {"candidates": items, "count": len(items)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def mark_consolidated(
    date_str: str, distilled_note_ids: list[str] | None = None
) -> dict[str, Any]:
    """Mark a daily note as consolidated. Requires distilled_note_ids for auditability."""
    from pkm.commands.consolidate import _parse_frontmatter, _set_frontmatter_field
    from datetime import date

    vault = _get_vault()
    try:
        if not distilled_note_ids:
            return {
                "error": "distilled_note_ids is required — provide IDs of notes created during distillation."
            }
        today = date.today().isoformat()
        if date_str == today:
            return {
                "error": "Cannot mark today's daily note as consolidated — it is still in use."
            }
        note_path = vault.daily_dir / f"{date_str}.md"
        if not note_path.exists():
            return {"error": f"Daily note not found: {date_str}.md"}
        missing = [
            nid
            for nid in distilled_note_ids
            if not (vault.notes_dir / f"{nid}.md").exists()
        ]
        if missing:
            return {"error": f"Distilled note IDs not found: {', '.join(missing)}"}
        text = note_path.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        if fm.get("consolidated", False):
            return {"status": "already_consolidated", "date": date_str}
        text = _set_frontmatter_field(text, "consolidated", True)
        text = _set_frontmatter_field(text, "distilled_to", distilled_note_ids)
        note_path.write_text(text, encoding="utf-8")
        return {
            "status": "consolidated",
            "date": date_str,
            "distilled_to": distilled_note_ids,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def read_recent_note_activity(tail: int = 20) -> dict[str, Any]:
    """Read the last N entries from the note operation log (.pkm/log.md). Best-effort only."""
    vault = _get_vault()
    try:
        log_path = vault.pkm_dir / "log.md"
        if not log_path.exists():
            return {"log": [], "message": "No activity log yet."}
        lines = log_path.read_text(encoding="utf-8").splitlines()
        non_empty = [line for line in lines if line.strip()]
        return {"log": non_empty[-tail:], "count": len(non_empty[-tail:])}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def find_surprising_connections(top_n: int = 20) -> dict[str, Any]:
    """Find notes that semantically bridge two different topic clusters (hidden cross-cluster links).

    Use when you want to discover non-obvious connections between different vault topic areas.
    Requires pkm index to have been run to build the enriched graph.
    """
    from pkm.tools.search import find_surprising_connections as _tool

    try:
        result = _tool(top_n=top_n)
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def list_clusters() -> dict[str, Any]:
    """List all topic clusters with membership stats, hub notes, and centroid drift.

    Use to understand vault thematic structure before create_hub_note() or find_surprising_connections().
    Requires pkm index to have been run.
    """
    from pkm.tools.search import list_clusters as _tool

    try:
        result = _tool()
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def list_god_nodes(top_n: int = 10) -> dict[str, Any]:
    """List the most connected notes by combined degree + betweenness centrality.

    Use to identify structural hub notes that hold the knowledge graph together.
    Requires pkm index to have been run.
    """
    from pkm.tools.search import list_god_nodes as _tool

    try:
        result = _tool(top_n=top_n)
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def create_hub_note(cluster_index: int, title: str, description: str) -> dict[str, Any]:
    """Create an index note that serves as the hub for a topic cluster.

    Use after list_clusters() identifies a cluster without a hub note.
    Requires pkm index to have been run to build the enriched graph.
    """
    from pkm.tools.search import create_hub_note as _tool

    try:
        result = _tool(
            cluster_index=cluster_index, title=title, description=description
        )
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def add_wikilink(
    source_note_id: str, target_note_id: str, description: str
) -> dict[str, Any]:
    """Append a [[target|description]] entry to the '## Related' section of source note.

    description MUST explain WHY the connection is meaningful — the conceptual bridge,
    not a description of the target note. Use after find_surprising_connections().
    """
    from pkm.tools.links import add_wikilink as _tool

    try:
        result = _tool(
            source_note_id=source_note_id,
            target_note_id=target_note_id,
            description=description,
        )
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}


def run_server(vault: VaultConfig) -> None:
    """Start the MCP stdio server bound to the given vault."""
    global _current_vault
    _current_vault = vault
    mcp.run(transport="stdio")
