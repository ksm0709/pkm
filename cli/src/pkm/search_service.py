"""In-process semantic search service shared by daemon surfaces."""

from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from pathlib import Path

from pkm.config import VaultConfig, discover_vaults
from pkm.search_engine import (
    IndexEntry,
    SearchResult,
    VectorIndex,
    _require_transformers,
    is_index_stale,
    search,
)

STALE_INDEX_WARNING = "Index may be out of date. Run 'pkm index' to rebuild."


@lru_cache(maxsize=2)
def get_cached_index(index_path: str, index_mtime: float) -> VectorIndex:
    """Load a vector index using the daemon process cache."""
    path = Path(index_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = [
        IndexEntry(
            **{k: v for k, v in e.items() if k in IndexEntry.__dataclass_fields__}
        )
        for e in data["entries"]
    ]
    return VectorIndex(
        model=data["model"],
        created_at=data["created_at"],
        entries=entries,
        schema_version=data.get("schema_version", 1),
    )


def resolve_search_vault(vault_name: str | None) -> VaultConfig | None:
    """Resolve an explicit vault name, falling back to the first configured vault."""
    vaults = discover_vaults()
    if vault_name and vault_name in vaults:
        return vaults[vault_name]
    return next(iter(vaults.values())) if vaults else None


async def run_in_process_search(
    query: str,
    vault: VaultConfig,
    top: int = 10,
    memory_type: str | None = None,
    min_importance: float = 1.0,
    recency_weight: float = 0.0,
) -> tuple[list[SearchResult], str | None]:
    """Search the daemon's cached index without round-tripping through its socket."""
    stale_warning = STALE_INDEX_WARNING if is_index_stale(vault) else None
    index_path = vault.pkm_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(index_path)

    index_mtime = index_path.stat().st_mtime
    _require_transformers("all-MiniLM-L6-v2")
    index = get_cached_index(str(index_path), index_mtime)

    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        None,
        lambda: search(
            query=query,
            index=index,
            top_n=top,
            min_importance=min_importance,
            memory_type_filter=memory_type,
            recency_weight=recency_weight,
        ),
    )
    return results, stale_warning
