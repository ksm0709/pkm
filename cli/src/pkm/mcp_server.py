"""MCP server exposing PKM vault tools for AI agents.

Runs as a foreground stdio server. An MCP client spawns this process via config:
    command = "pkm"
    args = ["mcp", "--vault", "my-vault"]
"""

from __future__ import annotations


from datetime import date, datetime
from typing import Any

import click
from mcp.server.fastmcp import FastMCP

from pkm.config import VaultConfig, get_vault
from pkm.credential_store import agent_credential_env

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


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


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
    """Create a permanent atomic note for reusable knowledge.

    Use for knowledge that will be referenced again: architectural decisions, bug root causes,
    API behaviors, patterns, user preferences. Search() first to avoid duplicates —
    update an existing note if the topic already exists.
    Do NOT use for ephemeral session logs — use daily_add() instead.

    importance: 1-3 trivial · 4-6 moderate · 7-8 important (arch decisions, bug root causes)
    · 9-10 critical (security, irreversible). Default 5 if unsure. Bias 7+ for anything the
    next agent would need.

    Args:
        content: Note body text (required).
        title: Note title. Auto-generated from content if omitted.
        type: Memory type — semantic (concepts/facts), episodic (events), procedural (how-to).
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
    """Append a timestamped log entry to today's daily note (ephemeral session log).

    Use for work summaries, observations, and progress notes that don't need independent
    future reference. This is the lightest PKM write and should be called at the END of
    every session. Do NOT use for reusable knowledge — use note_add() instead.
    To READ a past daily note, use read_daily_log(offset=N).

    Args:
        text: The text to log. Keep to 1-3 sentences summarizing what was done.
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
def read_daily_log(
    offset: int = 0,
    date_str: str | None = None,
) -> dict[str, Any]:
    """Read a daily note for past or present (read-only context retrieval).

    Use BEFORE starting work to recall what happened yesterday or N days ago — pulls
    the full daily log so the agent can pick up where the previous session left off.
    Most common: offset=1 (yesterday) at session start.

    Trigger condition: user references prior work ("어제", "지난번", "yesterday",
        "what did we do"), or you need to chain context across sessions.
    Anti-case: do NOT call repeatedly in a loop scanning many days — use offset with
        a specific N. For multi-day search, prefer search() or pkm_ask().
    Workflow position: SESSION-START context recall, before any write operation.

    Args:
        offset: Days before today. 0=today, 1=yesterday, N=N days ago. Default 0.
        date_str: Explicit date in YYYY-MM-DD format. Takes precedence over offset.

    Returns:
        dict with status, date, and content (or message if not found).
    """
    from pkm.commands.daily import resolve_target_date

    vault = _get_vault()
    try:
        target = resolve_target_date(date_str, offset)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    note_path = vault.daily_dir / f"{target}.md"
    if not note_path.exists():
        return {
            "status": "not_found",
            "date": target,
            "message": f"No daily note for {target}",
        }
    try:
        return {
            "status": "ok",
            "date": target,
            "content": note_path.read_text(encoding="utf-8"),
        }
    except Exception as e:
        return {"status": "error", "date": target, "message": str(e)}


@mcp.tool()
def create_daily_subnote(
    title: str,
    content: str,
    tags: list[str] | None = None,
    aliases: list[str] | None = None,
) -> dict[str, Any]:
    """Create a dated subnote linked from today's daily note (medium-weight session record).

    Use for session-scoped records larger than a daily_add() entry but not warranting
    a standalone atomic note — meeting notes, investigation logs, design explorations.
    Creates YYYY-MM-DD-{title}.md in the vault daily directory and appends a timestamped
    [[wikilink]] entry to today's daily note.
    For permanent reusable knowledge, use note_add() instead.
    To READ a past daily note, use read_daily_log(offset=N).

    Args:
        title: Subnote title slug (spaces become hyphens).
        content: Markdown body content for the new subnote.
        tags: Optional list of tags for the subnote frontmatter.
        aliases: Optional list of aliases for the subnote frontmatter.
    """
    import re as _re
    from datetime import datetime as _dt
    from pkm.commands.daily import (
        _make_subnote_content,
        DAILY_TEMPLATE,
        _add_subnote_link,
    )

    vault = _get_vault()
    try:
        today = _dt.now().strftime("%Y-%m-%d")
        now = _dt.now().strftime("%H:%M:%S")

        title_slug = _re.sub(r"[/\\]", "", title.replace(" ", "-"))
        title_slug = _re.sub(r"\.\.+", "", title_slug).strip("-").strip()
        if not title_slug:
            return {"error": "title cannot be empty"}

        note_id = f"{today}-{title_slug}"
        note_path = vault.daily_dir / f"{note_id}.md"

        vault.daily_dir.mkdir(parents=True, exist_ok=True)
        if not str(note_path.resolve()).startswith(str(vault.daily_dir.resolve())):
            return {"error": "invalid title — would escape daily directory"}

        if not note_path.exists():
            note_path.write_text(
                _make_subnote_content(note_id, content, tags, aliases), encoding="utf-8"
            )

        daily_path = vault.daily_dir / f"{today}.md"
        if not daily_path.exists():
            daily_path.write_text(DAILY_TEMPLATE.format(date=today), encoding="utf-8")

        _add_subnote_link(daily_path, now, note_id)
        return {"status": "created", "note_id": note_id, "path": str(note_path)}
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
    """Search vault notes by topic or concept (semantic similarity).

    Use BEFORE starting any non-trivial task to recall prior knowledge, decisions,
    and patterns. Also use before note_add() to check for duplicates.
    Do NOT use when you already know the exact note slug — use get_note_neighbors() instead.
    Typically followed by get_note_neighbors() on relevant results.

    Args:
        query: Free-text concept or topic to search for.
        top: Maximum number of results (default 10, max 50).
        vault: Vault name for cross-vault search. Uses server vault if omitted.
        memory_type: Filter by type — semantic, episodic, or procedural.
        min_importance: Minimum importance score filter (default 1.0). Use 5.0 to focus on non-trivial notes.
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
        from pkm.tools.links import _get_note_neighbors_data

        def _related(r):
            try:
                return _get_note_neighbors_data(
                    target_vault, r.note_id, include_semantic=True
                )
            except Exception:
                return None

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
                    "related_notes": _related(r),
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
    """Ask a natural language question and get a synthesized answer from vault notes (RAG).

    Use when you need an answer synthesized across multiple notes — prior decisions,
    user preferences, patterns. Slower than search() but returns a direct answer.
    Safe to run as a background task while other work continues.
    Do NOT use as a substitute for search() — use search() for exploration, pkm_ask() for questions.

    Args:
        query: The natural language question to ask.
        vault: Vault name for cross-vault search. Uses server vault if omitted.
        model: Optional LLM model to use. Overrides config if provided.
        timeout: Timeout in seconds to wait for the result (default 120).
    """
    import json
    import asyncio
    from pathlib import Path
    from pkm.config import load_config

    target_vault = _get_vault(vault)
    sock_path = Path.home() / ".config" / "pkm" / "daemon.sock"

    config_model = load_config().get("defaults", {}).get("model")
    final_model = model or config_model or "auto"
    graph_depth = load_config().get("defaults", {}).get("graph-depth", 0)

    env_keys = agent_credential_env()

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
def read_note(note_id: str, vault: str | None = None) -> dict[str, Any]:
    """Read the full content and metadata of a note by ID.

    Returns a structured dict with 8 keys: note_id, title, body, frontmatter,
    created, updated, tags, importance.  Use after search() or list_notes() to
    fetch the full note body before editing or linking.

    Args:
        note_id: The note slug without .md extension (e.g. "2026-04-05-my-note").
        vault: Vault name. Uses server vault if omitted.
    """
    from pkm.frontmatter import parse

    target_vault = _get_vault(vault)
    for base_dir in [target_vault.notes_dir, target_vault.daily_dir]:
        path = base_dir / f"{note_id}.md"
        if path.exists():
            try:
                note = parse(path)
                fm = note.meta if note.meta else {}
                importance_raw = fm.get("importance")
                importance = int(importance_raw) if importance_raw is not None else None
                return {
                    "note_id": str(note.id),
                    "title": note.title,
                    "body": note.body,
                    "frontmatter": _json_safe(fm),
                    "created": fm.get("created_at") or fm.get("source") or None,
                    "updated": fm.get("updated_at") or None,
                    "tags": note.tags,
                    "importance": importance,
                    "content_hash": _note_hash(fm, note.body),
                }
            except Exception as e:
                return {"error": str(e)}
    return {"error": f"Note '{note_id}' not found."}


def _note_hash(meta: dict[str, Any], body: str) -> str:
    import hashlib
    from pkm.frontmatter import render

    return hashlib.sha256(render(meta, body).encode("utf-8")).hexdigest()


@mcp.tool()
def patch_note(
    note_id: str,
    operation: str,
    old: str | None = None,
    new: str | None = None,
    section: str | None = None,
    fields: dict[str, Any] | None = None,
    expected_occurrences: int = 1,
    base_hash: str | None = None,
) -> dict[str, Any]:
    """Patch part of a note without rewriting the full body.

    Use this for partial edits to existing notes: exact replacement, append/prepend,
    section upsert, or frontmatter updates. Do NOT use this to create notes; use
    note_add for new atomic notes and daily_add for logs.

    Args:
        note_id: Note slug without .md.
        operation: replace, append, prepend, upsert_section, or frontmatter.
        old: Existing exact body text for replace.
        new: New body text for replace/append/prepend/upsert_section.
        section: Markdown section heading for section-scoped operations.
        fields: Frontmatter fields to merge when operation is frontmatter.
        expected_occurrences: Required exact match count for replace.
        base_hash: Optional stale-write guard from read_note content_hash.
    """
    from pkm.tools.notes import _patch_note_impl

    target_vault = _get_vault()
    try:
        return _patch_note_impl(
            target_vault,
            note_id=note_id,
            operation=operation,  # type: ignore[arg-type]
            old=old,
            new=new,
            section=section,
            fields=fields,
            expected_occurrences=expected_occurrences,
            base_hash=base_hash,
        )
    except Exception as e:
        return {"status": "error", "error": str(e), "summary": str(e)}


@mcp.tool()
def rename_note(
    old_note_id: str,
    new_note_id: str,
    vault: str | None = None,
) -> dict[str, Any]:
    """Rename a note ID and update every wikilink that points to it.

    Args:
        old_note_id: Current note ID, without .md.
        new_note_id: New note ID, without .md.
        vault: Vault name. Uses server vault if omitted.
    """
    from pkm.note_lifecycle import rename_note_id

    target_vault = _get_vault(vault)
    try:
        result = rename_note_id(target_vault, old_note_id, new_note_id)
        return {
            "status": "renamed",
            "old_note_id": result.old_note_id,
            "new_note_id": result.new_note_id,
            "old_path": result.old_path,
            "new_path": result.new_path,
            "wikilinks_updated": result.wikilinks.replacements,
            "files_updated": result.wikilinks.changed_files,
        }
    except (ValueError, FileNotFoundError, FileExistsError) as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def list_notes(filter: str | None = None, vault: str | None = None) -> dict[str, Any]:
    """List notes in the vault, optionally filtered by title substring.

    Returns {notes: [{note_id, title, path, tags, created_at}], count: N}.
    Use to enumerate notes before bulk operations or when you don't have a
    specific search query. For semantic lookup use search() instead.

    Args:
        filter: Optional case-insensitive title substring filter.
        vault: Vault name. Uses server vault if omitted.
    """
    from pkm.frontmatter import parse

    target_vault = _get_vault(vault)
    results = []
    if not target_vault.notes_dir.is_dir():
        return {"notes": results, "count": 0}

    filter_lower = filter.lower() if filter else None
    for md_file in sorted(target_vault.notes_dir.glob("*.md")):
        try:
            note = parse(md_file)
            if filter_lower and filter_lower not in note.title.lower():
                continue
            fm = note.meta if note.meta else {}
            results.append(
                {
                    "note_id": note.id,
                    "title": note.title,
                    "path": str(md_file),
                    "tags": note.tags,
                    "created_at": fm.get("created_at") or fm.get("source") or None,
                }
            )
        except Exception:
            pass
    return {"notes": results, "count": len(results)}


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
    """List all orphan notes — notes with zero inbound AND zero outbound wikilinks.

    Use during vault maintenance to find disconnected knowledge that has become dead.
    Orphan notes are candidates for deletion, consolidation, or connecting via add_wikilink().
    Not needed in normal task workflows.
    """
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
    """Explore the connection graph around a specific note.

    Use after search() when a result looks relevant — traverse its outbound links,
    inbound backlinks, and optionally semantic connections for deeper context.
    This is the second step in tree-traversal knowledge collection:
    search() → get_note_neighbors() → get_note_neighbors() (one more level if needed, max 2-depth).
    Do NOT use include_semantic=True unless embedding-based connections are specifically needed; it is slower.

    Returns {note_id, outbound:[{note_id,title,type}], inbound:[{note_id,title,type}],
    semantic:[{note_id,title,type,confidence}]}. Requires pkm index to have been run.

    Args:
        note_id: Note slug without extension (e.g. "2026-04-05-my-note").
        include_semantic: Include embedding-based semantic connections (default False).
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
    """Mark a daily note as consolidated after Zettelkasten distillation.

    Call AFTER creating atomic notes from a daily note's content (note_add()), providing
    the IDs of the notes created. Part of the zettel-loop workflow:
    list_consolidation_candidates() → distill → note_add() → mark_consolidated().
    Requires distilled_note_ids for auditability — cannot mark without them.

    Args:
        date_str: Date of the daily note to mark (format: YYYY-MM-DD).
        distilled_note_ids: IDs of atomic notes created during distillation (required).
    """
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

    Use for on-demand cross-domain connection discovery. The daemon runs this periodically
    in the background — call manually only when you suspect an important connection exists
    or want an immediate scan. Results can then be linked with add_wikilink().
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

    Use after note_add() when the new note has an obvious meaningful connection to an existing note.
    description MUST explain WHY the connection is meaningful — the conceptual bridge,
    not a description of the target. Example: "shares vault-scoped path resolution pattern"
    not "another note about vault paths". The daemon discovers non-obvious links periodically;
    manual use here is for connections you already know about.

    Args:
        source_note_id: Note slug to add the link to (without .md extension).
        target_note_id: Note slug to link to (without .md extension).
        description: WHY this connection is meaningful (required).
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
