import os
from pathlib import Path
from tiny_agent.agent import tool
from pkm.config import VaultConfig
from pkm.search_engine import search_via_daemon, load_index, search as search_fn


def _get_vault(vault_dir: str) -> VaultConfig:
    return VaultConfig(name=Path(vault_dir).name, path=Path(vault_dir))


@tool
def semantic_search(
    query: str,
    top: int = 5,
    memory_type: str | None = None,
    min_importance: float = 1.0,
    vault_dir: str | None = None,
) -> str:
    """Search vault notes semantically.

    Args:
        query: The search query.
        top: Number of results to return.
        memory_type: Optional filter by memory type ('episodic', 'semantic', 'procedural').
        min_importance: Minimum importance score (1.0 to 10.0).
        vault_dir: The vault directory path. If not provided, uses PKM_VAULT_DIR env var.
    """
    v_dir = vault_dir or os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)

    try:
        results = search_via_daemon(
            query,
            vault,
            top_n=top,
            min_importance=min_importance,
            memory_type_filter=memory_type,
        )

        if results is None:
            vector_index = load_index(vault)
            results = search_fn(
                query,
                vector_index,
                top_n=top,
                memory_type_filter=memory_type,
                min_importance=min_importance,
            )

        if not results:
            return "No results found."

        items = []
        for r in results:
            desc = getattr(r, "description", "") or ""
            if not desc:
                try:
                    from pkm.frontmatter import parse as parse_note

                    note = parse_note(Path(r.path))
                    desc = note.meta.get("description") or note.body.strip()[:200]
                except Exception:
                    pass
            items.append(f"Title: {r.title}\nScore: {r.score:.4f}\nDescription: {desc}")

        return "\n\n".join(items)
    except Exception as e:
        return f"Error performing semantic search: {str(e)}"
