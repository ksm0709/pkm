"""Note commands for PKM CLI."""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import re
import shlex
import subprocess
import sys
from datetime import date
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from pkm.config import load_config
from pkm.editor import get_editor
from pkm.frontmatter import (
    generate_frontmatter,
    generate_memory_frontmatter,
    parse,
    render,
)
from pkm.wikilinks import find_backlinks
from pkm.commands.maintenance import stale
from pkm.commands.links import orphans

console = Console()


def create_note(
    vault,
    title: str | None = None,
    content: str | None = None,
    memory_type: str | None = None,
    importance: int | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
    tags: list[str] | None = None,
    no_dedup: bool = False,
    meta: dict | None = None,
    source: str | None = None,
) -> Path:
    """Create an atomic note in the vault. Click-free canonical implementation.

    Called by both the CLI ``note add`` command and the MCP ``note_add`` tool.
    Future changes to note creation logic should target this function.

    Returns the path to the created note file.
    Raises ``ValueError`` for bad input, ``FileExistsError`` if the note already exists.
    """
    if content and not title:
        effective_title = content[:50]
    elif title:
        effective_title = title
    else:
        raise ValueError("Provide a title, or use content for agent usage")

    if not no_dedup and content:
        try:
            from pkm.search_engine import load_index, find_similar, search_via_daemon

            _matches = search_via_daemon(content, vault, top_n=1)
            if _matches is not None:
                _matches = [m for m in _matches if m.score >= 0.85]
            else:
                _index = load_index(vault)
                _matches = find_similar(content, _index, threshold=0.85, top_n=1)

            if _matches:
                pass  # similar notes found but dedup not yet implemented
        except Exception:
            pass

    today = date.today().isoformat()
    slug = _slugify(effective_title)
    filename = f"{today}-{slug}.md"
    note_path: Path = vault.notes_dir / filename
    note_id = note_path.stem

    if note_path.exists():
        raise FileExistsError(f"Note already exists: {note_path}")

    tag_list = tags or []
    body = content or ""
    extra = dict(meta) if meta else {}

    is_memory = bool(content or memory_type or importance is not None or session_id)
    if is_memory:
        from datetime import datetime, timezone

        fm = generate_memory_frontmatter(
            note_id=note_id,
            memory_type=memory_type or "semantic",
            importance=float(importance) if importance is not None else 5.0,
            created_at=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            agent_id=agent_id,
            source_type="agent",
            tags=tag_list,
            **extra,
        )
    else:
        fm = generate_frontmatter(
            note_id,
            tags=tag_list,
            aliases=[],
            source=source or today,
            **extra,
        )

    note_content = render(fm, body)
    note_path.write_text(note_content, encoding="utf-8")
    _append_operation_log(vault, "add", note_id, effective_title)

    try:
        from pkm.search_engine import update_index_via_daemon

        update_index_via_daemon(vault)
    except Exception:
        pass

    return note_path


def _slugify(title: str) -> str:
    """Convert title to filename slug."""
    lowered = title.lower().replace(" ", "-")
    ascii_slug = re.sub(r"[^a-z0-9-]", "", lowered)
    ascii_slug = re.sub(r"-+", "-", ascii_slug).strip("-")
    if ascii_slug:
        return ascii_slug
    return title.replace(" ", "-")


def _search_notes(vault, query: str) -> list:
    """Search notes by title (case-insensitive partial match)."""
    if not vault.notes_dir.is_dir():
        return []
    query_lower = query.lower()
    matches = []
    for md_file in sorted(vault.notes_dir.glob("*.md")):
        try:
            note = parse(md_file)
            if query_lower in note.title.lower():
                matches.append(note)
        except Exception:
            pass
    return matches


def _append_operation_log(vault, operation: str, note_id: str, title: str) -> None:
    """Append a timestamped entry to .pkm/log.md. Silently ignores all errors."""
    try:
        from datetime import datetime, date as _date

        today = _date.today().isoformat()
        now = datetime.now().strftime("%H:%M")
        log_path = vault.pkm_dir / "log.md"
        vault.pkm_dir.mkdir(parents=True, exist_ok=True)
        entry = f'- {now} [{operation}] {note_id} — "{title}"\n'
        date_header = f"## {today}"
        if log_path.exists():
            text = log_path.read_text(encoding="utf-8")
            if date_header in text:
                text = text.replace(f"{date_header}\n", f"{date_header}\n{entry}", 1)
            else:
                if not text.endswith("\n"):
                    text += "\n"
                text += f"\n{date_header}\n{entry}"
        else:
            text = f"# Operation Log\n\n{date_header}\n{entry}"
        log_path.write_text(text, encoding="utf-8")
    except Exception:
        pass


@click.group(invoke_without_command=True)
@click.pass_context
def note(ctx: click.Context) -> None:
    """Manage notes."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@note.command()
@click.argument("title", required=False, default=None)
@click.option(
    "--content",
    default=None,
    help="Note content body (agent usage; title auto-generated from content)",
)
@click.option("--stdin", "use_stdin", is_flag=True, help="Read content from stdin")
@click.option(
    "--type",
    "memory_type",
    type=click.Choice(["episodic", "semantic", "procedural"]),
    default=None,
)
@click.option("--importance", type=click.IntRange(1, 10), default=None)
@click.option("--session", "session_id", default=None)
@click.option("--agent", "agent_id", default=None)
@click.option("--tags", "-t", default="", help="Comma-separated tags")
@click.option(
    "--no-dedup", is_flag=True, default=False, help="Skip duplicate detection"
)
@click.option(
    "--meta",
    "meta_pairs",
    multiple=True,
    help="key=value metadata pairs for frontmatter",
)
@click.pass_context
def add(
    ctx: click.Context,
    title: str | None,
    content: str | None,
    use_stdin: bool,
    memory_type: str | None,
    importance: int | None,
    session_id: str | None,
    agent_id: str | None,
    tags: str,
    no_dedup: bool,
    meta_pairs: tuple[str, ...],
) -> None:
    """Create a new atomic note in the vault.

    Human usage (title required):
      pkm note add "My Research Note" --tags ai

    Agent usage (--content generates title automatically):
      pkm note add --content "learned X" --type semantic --importance 7
      echo "multi-line" | pkm note add --stdin --type episodic --importance 5

    Custom metadata:
      pkm note add --content "fact" --meta source=agent1 --meta event_type=goal
    """
    if use_stdin:
        content = sys.stdin.read().strip()

    vault = ctx.obj["vault"]
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    meta = (
        {k: v for k, _, v in (p.partition("=") for p in meta_pairs) if k}
        if meta_pairs
        else None
    )

    try:
        note_path = create_note(
            vault=vault,
            title=title,
            content=content,
            memory_type=memory_type,
            importance=importance,
            session_id=session_id,
            agent_id=agent_id,
            tags=tag_list,
            no_dedup=no_dedup,
            meta=meta,
        )
    except ValueError as e:
        raise click.UsageError(str(e))
    except FileExistsError as e:
        raise click.ClickException(str(e))

    console.print(f"[green]Created[/green] {note_path}")


@note.command()
@click.argument("query")
@click.pass_context
def edit(ctx: click.Context, query: str) -> None:
    """Open a note in the editor (search by title, first match)."""
    vault = ctx.obj["vault"]
    matches = _search_notes(vault, query)
    if not matches:
        console.print(f"[red]No notes found matching '{query}'[/red]")
        raise SystemExit(1)
    selected = matches[0]
    config_data = load_config()
    editor_cmd = get_editor(config_data)
    result = subprocess.run([*shlex.split(editor_cmd), str(selected.path)])
    if result.returncode != 0:
        console.print(f"[yellow]Editor exited with code {result.returncode}[/yellow]")


@note.command()
@click.argument("query")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "md"]),
    default="json",
    show_default=True,
    help="Output format: json (default, machine-readable) or md (markdown content)",
)
@click.option(
    "--top",
    "-n",
    default=5,
    show_default=True,
    help="Max number of notes to return (json mode)",
)
@click.option("--depth", type=int, default=1, help="Graph traversal depth")
@click.pass_context
def show(
    ctx: click.Context, query: str, output_format: str, top: int, depth: int
) -> None:
    """Show note contents. Default: JSON array of matching notes.

    Agent usage (JSON, default):
      pkm note show "pkm"

    Human usage (markdown):
      pkm note show "pkm" --format md
    """
    vault = ctx.obj["vault"]
    matches = _search_notes(vault, query)

    if not matches:
        if output_format == "json":
            payload = {"query": query, "result_count": 0, "notes": []}
            click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            console.print(f"[red]No notes found matching '{query}'[/red]")
            raise SystemExit(1)
        return

    if output_format == "md":
        selected = matches[0]
        console.print(selected.path.read_text(encoding="utf-8"), end="")
        return

    limited = matches[:top]
    items = []
    for n in limited:
        backlink_paths = find_backlinks(vault, n.id)
        backlink_titles = []
        for bp in backlink_paths:
            try:
                bl_note = parse(bp)
                backlink_titles.append(bl_note.title)
            except Exception:
                pass

        graph_context = None
        try:
            from pkm.search_engine import get_graph_context_via_daemon

            graph_context = get_graph_context_via_daemon(n.id, vault, depth)
        except Exception:
            pass

        items.append(
            {
                "title": n.title,
                "note_id": n.id,
                "description": n.description,
                "body": n.body,
                "frontmatter": n.meta,
                "backlinks": backlink_titles,
                "graph_context": graph_context,
            }
        )

    payload = {
        "query": query,
        "result_count": len(items),
        "notes": items,
    }
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    click.echo("")
    click.echo("* Edit note: pkm note edit <title>")
    click.echo("* Find related: pkm search <keyword>")
    click.echo("* View backlink: pkm note show <backlink-title>")


@note.command(name="search")
@click.argument("query")
@click.option("--top", "-n", default=5, show_default=True, help="Number of results")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format",
)
@click.option(
    "--type",
    "memory_type",
    type=click.Choice(["episodic", "semantic", "procedural"]),
    default=None,
)
@click.option("--min-importance", type=float, default=None)
@click.pass_context
def note_search(
    ctx: click.Context,
    query: str,
    top: int,
    output_format: str,
    memory_type: str | None,
    min_importance: float | None,
) -> None:
    """Search notes semantically (default: JSON output for agents)."""
    from pkm.commands.search import format_search_results
    from pkm.search_engine import is_index_stale, load_index, search as search_fn

    vault = ctx.obj["vault"]

    stale_warning: str | None = None
    if is_index_stale(vault):
        stale_warning = "Index may be out of date. Run 'pkm index' to rebuild."

    min_imp = min_importance if min_importance is not None else 1.0

    if output_format == "json":
        logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
        logging.getLogger("transformers").setLevel(logging.ERROR)
        logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

        _buf = io.StringIO()
        _err_buf = io.StringIO()
        with contextlib.redirect_stdout(_buf), contextlib.redirect_stderr(_err_buf):
            vector_index = load_index(vault)
            results = search_fn(
                query,
                vector_index,
                top_n=top,
                memory_type_filter=memory_type,
                min_importance=min_imp,
            )
    else:
        if stale_warning:
            console.print(f"[yellow]Warning:[/yellow] {stale_warning}")
            stale_warning = None
        vector_index = load_index(vault)
        results = search_fn(
            query,
            vector_index,
            top_n=top,
            memory_type_filter=memory_type,
            min_importance=min_imp,
        )

    if not results and output_format != "json":
        console.print("[yellow]No results found.[/yellow]")
        return

    format_search_results(
        query=query,
        results=results,
        output_format=output_format,
        console=console,
        vault=vault,
        stale_warning=stale_warning,
    )


@note.command()
@click.argument("query")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format",
)
@click.pass_context
def links(ctx: click.Context, query: str, output_format: str) -> None:
    """Show backlinks for a note."""
    vault = ctx.obj["vault"]
    matches = _search_notes(vault, query)
    if not matches:
        if output_format == "json":
            print(
                json.dumps(
                    {"error": f"No notes found matching '{query}'"},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            console.print(f"[red]No notes found matching '{query}'[/red]")
        raise SystemExit(1)
    selected = matches[0]

    backlink_paths = find_backlinks(vault, selected.id)

    if output_format == "json":
        items = []
        for bp in backlink_paths:
            try:
                bl_note = parse(bp)
                items.append(
                    {
                        "title": bl_note.title,
                        "description": bl_note.description or "",
                        "path": bp.name,
                    }
                )
            except Exception:
                pass
        print(
            json.dumps(
                {"note": selected.title, "backlinks": items, "count": len(items)},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if not backlink_paths:
            console.print(f"[dim]No backlinks found for '{selected.title}'[/dim]")
            return

        table = Table(title=f"Backlinks for '{selected.title}'")
        table.add_column("Title", style="cyan")
        table.add_column("Description", style="dim")
        table.add_column("Path", style="dim")

        for bp in backlink_paths:
            try:
                bl_note = parse(bp)
                table.add_row(bl_note.title, bl_note.description or "", bp.name)
            except Exception:
                pass

        console.print(table)


@note.command(name="log")
@click.option(
    "--tail", default=20, show_default=True, help="Number of recent entries to show"
)
@click.pass_context
def note_log(ctx: click.Context, tail: int) -> None:
    """Show recent note operation log from .pkm/log.md."""
    vault = ctx.obj["vault"]
    log_path = vault.pkm_dir / "log.md"
    if not log_path.exists():
        click.echo(
            "No log file yet. Log entries appear after your first `pkm note add`."
        )
        return
    lines = log_path.read_text(encoding="utf-8").splitlines()
    non_empty = [line for line in lines if line.strip()]
    shown = non_empty[-tail:] if tail < len(non_empty) else non_empty
    click.echo("\n".join(shown))


@note.command(name="auto-link")
@click.argument("note_id", required=False)
@click.option("--all", "all_notes", is_flag=True, help="Process all notes")
@click.option("--dry-run", is_flag=True, required=True, help="Mandatory dry-run mode")
@click.pass_context
def auto_link(
    ctx: click.Context, note_id: str | None, all_notes: bool, dry_run: bool
) -> None:
    """Auto-link plain text matching other notes' titles."""
    if not note_id and not all_notes:
        raise click.UsageError("Must provide either note_id or --all")

    vault = ctx.obj["vault"]
    from pkm.graph import ASTCache

    db_path = vault.pkm_dir / "ast.db"
    if not db_path.exists():
        console.print("[red]AST cache not found. Run 'pkm index' first.[/red]")
        raise SystemExit(1)

    cache = ASTCache(db_path)
    all_notes_list = _search_notes(vault, "")
    titles = {n.title: n.id for n in all_notes_list if n.title}

    notes_to_process = (
        all_notes_list if all_notes else [n for n in all_notes_list if n.id == note_id]
    )

    for n in notes_to_process:
        metadata = cache.get(n.id)
        if not metadata:
            continue

        file_path = Path(metadata.path)
        content = file_path.read_text(encoding="utf-8")
        new_content = content

        import re

        m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", content, re.DOTALL)
        body_offset = m.end() if m else 0

        offsets = sorted(
            metadata.plain_text_offsets, key=lambda x: x.get("offset", 0), reverse=True
        )

        for offset_info in offsets:
            text = offset_info["text"]
            offset = offset_info.get("offset", 0) + body_offset
            length = offset_info.get("length", len(text))

            if not text.strip():
                continue

            new_text = text
            for title in titles.keys():
                if title != n.title and title in new_text:
                    if f"[[{title}]]" not in new_text:
                        new_text = new_text.replace(title, f"[[{title}]]")

            if new_text != text:
                new_content = (
                    new_content[:offset] + new_text + new_content[offset + length :]
                )

        if new_content != content:
            if dry_run:
                console.print(f"[yellow]Would update links in {n.id}[/yellow]")
            else:
                file_path.write_text(new_content, encoding="utf-8")
                console.print(f"[green]Updated links in {n.id}[/green]")


@note.command(name="split")
@click.argument("note_id", required=False)
@click.option("--all", "all_notes", is_flag=True, help="Process all notes")
@click.option("--dry-run", is_flag=True, required=True, help="Mandatory dry-run mode")
@click.pass_context
def split_note(
    ctx: click.Context, note_id: str | None, all_notes: bool, dry_run: bool
) -> None:
    """Split notes into smaller atomic notes."""
    if not note_id and not all_notes:
        raise click.UsageError("Must provide either note_id or --all")

    vault = ctx.obj["vault"]
    from pkm.graph import ASTCache

    db_path = vault.pkm_dir / "ast.db"
    cache = ASTCache(db_path) if db_path.exists() else None

    all_notes_list = _search_notes(vault, "")
    notes_to_process = (
        all_notes_list if all_notes else [n for n in all_notes_list if n.id == note_id]
    )

    for n in notes_to_process:
        file_path = Path(n.path)
        content = file_path.read_text(encoding="utf-8")

        parts = []
        is_semantic = False
        metadata = cache.get(n.id) if cache else None

        if metadata and metadata.plain_text_offsets:
            try:
                from pkm.search_engine import _require_transformers

                blocks = [
                    info["text"]
                    for info in metadata.plain_text_offsets
                    if info["text"].strip()
                ]
                if len(blocks) > 1:
                    model = _require_transformers("all-MiniLM-L6-v2")
                    import numpy as np

                    embeddings = model.encode(blocks, show_progress_bar=False)

                    current_part = blocks[0]
                    for i in range(1, len(blocks)):
                        emb1 = np.array(embeddings[i - 1])
                        emb2 = np.array(embeddings[i])
                        norm1 = np.linalg.norm(emb1)
                        norm2 = np.linalg.norm(emb2)
                        if norm1 == 0 or norm2 == 0:
                            sim = 0.0
                        else:
                            sim = np.dot(emb1, emb2) / (norm1 * norm2)

                        if sim < 0.5:
                            parts.append(current_part)
                            current_part = blocks[i]
                        else:
                            current_part += "\n\n" + blocks[i]
                    parts.append(current_part)
                    is_semantic = True
            except Exception:
                parts = []

        if len(parts) <= 1:
            import re

            parts = re.split(r"\n## ", content)
            is_semantic = False

        if len(parts) <= 1:
            continue

        if dry_run:
            console.print(
                f"[yellow]Would split {n.id} into {len(parts)} notes[/yellow]"
            )
            continue

        bak_path = file_path.with_suffix(".md.bak")
        bak_path.write_text(content, encoding="utf-8")
        console.print(f"[dim]Created backup {bak_path.name}[/dim]")

        for i, part in enumerate(parts):
            if i == 0:
                file_path.write_text(part, encoding="utf-8")
            else:
                lines = part.strip().split("\n")
                heading = lines[0].strip()
                import re

                heading_clean = re.sub(r"^#+\s*", "", heading)
                child_slug = _slugify(heading_clean)
                if not child_slug:
                    child_slug = f"part-{i}"
                child_id = f"{n.id}-{child_slug}"
                child_path = vault.notes_dir / f"{child_id}.md"

                if is_semantic:
                    child_content = part
                else:
                    child_content = f"## {part}"

                from pkm.frontmatter import generate_frontmatter, render

                fm = generate_frontmatter(
                    child_id, tags=n.tags, aliases=[], source=n.id
                )
                final_content = render(fm, child_content)

                child_path.write_text(final_content, encoding="utf-8")
                console.print(f"[green]Created child note {child_id}[/green]")


note.add_command(stale)
note.add_command(orphans)
