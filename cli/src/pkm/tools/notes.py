import os
from pathlib import Path
from tiny_agent.tools import tool
from pkm.config import VaultConfig
from pkm.commands.notes import create_note, _search_notes


def _get_vault(vault_dir: str) -> VaultConfig:
    return VaultConfig(name=Path(vault_dir).name, path=Path(vault_dir))


@tool
def add_note(
    title: str,
    content: str,
    tags: list[str] | None = None,
    memory_type: str | None = None,
    importance: int | None = None,
) -> str:
    """Create a new atomic note in the vault.

    Args:
        title: The title of the note.
        content: The body content of the note.
        tags: Optional list of tags.
        memory_type: Optional memory type (e.g., 'semantic', 'episodic', 'procedural').
        importance: Optional importance score (1-10).
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)
    try:
        note_path = create_note(
            vault=vault,
            title=title,
            content=content,
            tags=tags,
            memory_type=memory_type,
            importance=importance,
        )
        return f"Successfully created note at {note_path}"
    except Exception as e:
        return f"Error creating note: {str(e)}"


@tool
def search_notes(query: str) -> str:
    """Search notes by title (case-insensitive partial match).

    Args:
        query: The search query.
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)
    try:
        matches = _search_notes(vault, query)
        if not matches:
            return f"No notes found matching '{query}'"

        results = []
        for n in matches[:5]:
            results.append(f"Title: {n.title}\nID: {n.id}\nContent:\n{n.body[:200]}...")
        return "\n\n".join(results)
    except Exception as e:
        return f"Error searching notes: {str(e)}"
