import json
import os
import re
from pathlib import Path

from tiny_agent.tools import tool

from pkm.config import VaultConfig


def _get_vault(vault_dir: str) -> VaultConfig:
    path = Path(vault_dir)
    return VaultConfig(name=path.name, path=path)


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
        items: list[dict[str, str]] = []
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


@tool()
def add_wikilink(source_note_id: str, target_note_id: str, description: str) -> str:
    """Append a [[target|description]] entry to the '## Related' section of source note.

    Creates the '## Related' section if it doesn't exist (at end of note body).
    description MUST explain WHY the connection is meaningful — the conceptual bridge,
    not a description of the target note.

    Good: "Both explore evaluation under uncertainty, one for ML models, one for decisions"
    Bad: "Related to software testing"

    Use this after find_surprising_connections() to promote semantic edges to explicit links.
    Returns success message with file path.

    Args:
        source_note_id: The note_id (filename without .md) of the note to add the link to.
        target_note_id: The note_id of the note to link to.
        description: WHY the connection is meaningful (the conceptual bridge).
    """
    try:
        vault = _get_vault(os.environ.get("PKM_VAULT_DIR", "."))

        # Find source note file
        source_path = next(
            (
                search_dir / f"{source_note_id}.md"
                for search_dir in (vault.notes_dir, vault.daily_dir)
                if (search_dir / f"{source_note_id}.md").exists()
            ),
            None,
        )
        if source_path is None:
            return f"Error: source note '{source_note_id}' not found."

        text = source_path.read_text(encoding="utf-8")
        link_entry = f"- [[{target_note_id}|{description}]]"

        # Check if ## Related section exists
        related_pattern = re.compile(r"^## Related\s*$", re.MULTILINE)
        match = related_pattern.search(text)
        if match:
            # Insert after the ## Related heading line
            insert_pos = match.end()
            # Skip blank lines immediately after the heading
            rest = text[insert_pos:]
            stripped_rest = rest.lstrip("\n")
            leading_newlines = len(rest) - len(stripped_rest)
            insert_at = insert_pos + leading_newlines
            text = text[:insert_at] + link_entry + "\n" + text[insert_at:]
        else:
            # Append ## Related section at end of file
            if not text.endswith("\n"):
                text += "\n"
            text += f"\n## Related\n\n{link_entry}\n"

        source_path.write_text(text, encoding="utf-8")
        return f"Added [[{target_note_id}]] to {source_path}"
    except Exception as e:
        return f"Error: {e}"
