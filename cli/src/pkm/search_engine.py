"""Semantic search engine for PKM vaults using sentence-transformers."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import click

from pkm.config import VaultConfig
from pkm.frontmatter import parse
from pkm.wikilinks import count_backlinks

try:
    from sentence_transformers import SentenceTransformer
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False

    class SentenceTransformer:  # type: ignore[no-redef]
        """Stub used when sentence-transformers is not installed."""

        def __init__(self, model_name: str) -> None:
            raise click.ClickException(
                "sentence-transformers is not installed. "
                "Install it with: uv pip install -e \".[search]\""
            )

        def encode(self, texts, **kwargs):  # pragma: no cover
            raise click.ClickException(
                "sentence-transformers is not installed. "
                "Install it with: uv pip install -e \".[search]\""
            )


@dataclass
class IndexEntry:
    note_id: str
    path: str
    embedding: list[float]
    backlink_count: int
    tags: list[str]
    title: str


@dataclass
class VectorIndex:
    model: str
    created_at: str
    entries: list[IndexEntry] = field(default_factory=list)


@dataclass
class SearchResult:
    note_id: str
    title: str
    score: float
    backlink_count: int
    tags: list[str]
    rank: int


def build_index(vault: VaultConfig, model_name: str = "all-MiniLM-L6-v2") -> VectorIndex:
    """Build a vector index for all notes and daily notes in the vault."""
    if not HAS_TRANSFORMERS:
        raise click.ClickException(
            "sentence-transformers is not installed. "
            "Install it with: uv pip install -e \".[search]\""
        )

    model = SentenceTransformer(model_name)
    backlink_counts = count_backlinks(vault)

    md_files: list[Path] = []
    for d in (vault.notes_dir, vault.daily_dir):
        if d.is_dir():
            md_files.extend(sorted(d.glob("*.md")))

    notes = [parse(f) for f in md_files]
    texts = [n.body.strip() or n.title for n in notes]

    embeddings = model.encode(texts, show_progress_bar=False)

    entries: list[IndexEntry] = []
    for note, emb in zip(notes, embeddings):
        note_id = str(note.id)
        entries.append(
            IndexEntry(
                note_id=note_id,
                path=str(note.path),
                embedding=emb.tolist(),
                backlink_count=backlink_counts.get(note_id, 0),
                tags=[str(t) for t in note.tags],
                title=str(note.title),
            )
        )

    index = VectorIndex(
        model=model_name,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        entries=entries,
    )

    vault.pkm_dir.mkdir(parents=True, exist_ok=True)
    index_path = vault.pkm_dir / "index.json"

    import datetime

    def _default(obj: object) -> str:
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return str(obj)
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    index_path.write_text(
        json.dumps(
            {
                "model": index.model,
                "created_at": index.created_at,
                "entries": [asdict(e) for e in index.entries],
            },
            ensure_ascii=False,
            default=_default,
        ),
        encoding="utf-8",
    )

    return index


def load_index(vault: VaultConfig) -> VectorIndex:
    """Load the vector index from disk."""
    index_path = vault.pkm_dir / "index.json"
    if not index_path.exists():
        raise click.ClickException(
            f"No index found at {index_path}. Run 'pkm index' first."
        )

    data = json.loads(index_path.read_text(encoding="utf-8"))
    entries = [IndexEntry(**e) for e in data["entries"]]
    return VectorIndex(
        model=data["model"],
        created_at=data["created_at"],
        entries=entries,
    )


def search(
    query: str,
    index: VectorIndex,
    top_n: int = 10,
    model_name: str = "all-MiniLM-L6-v2",
) -> list[SearchResult]:
    """Search the index for notes semantically similar to the query."""
    if not HAS_TRANSFORMERS:
        raise click.ClickException(
            "sentence-transformers is not installed. "
            "Install it with: uv pip install -e \".[search]\""
        )

    import numpy as np

    model = SentenceTransformer(model_name)
    query_emb = model.encode([query], show_progress_bar=False)[0]

    scored: list[tuple[float, IndexEntry]] = []
    for entry in index.entries:
        emb = np.array(entry.embedding, dtype=float)
        q = np.array(query_emb, dtype=float)
        norm_e = np.linalg.norm(emb)
        norm_q = np.linalg.norm(q)
        if norm_e == 0 or norm_q == 0:
            score = 0.0
        else:
            score = float(np.dot(q, emb) / (norm_q * norm_e))
        scored.append((score, entry))

    # Sort by score DESC, then backlink_count DESC for ties
    scored.sort(key=lambda x: (x[0], x[1].backlink_count), reverse=True)

    results: list[SearchResult] = []
    for rank, (score, entry) in enumerate(scored[:top_n], start=1):
        results.append(
            SearchResult(
                note_id=entry.note_id,
                title=entry.title,
                score=score,
                backlink_count=entry.backlink_count,
                tags=entry.tags,
                rank=rank,
            )
        )

    return results


def is_index_stale(vault: VaultConfig) -> bool:
    """Return True if any .md file is newer than the index."""
    index_path = vault.pkm_dir / "index.json"
    if not index_path.exists():
        return True

    index_mtime = index_path.stat().st_mtime

    for d in (vault.notes_dir, vault.daily_dir):
        if not d.is_dir():
            continue
        for md_file in d.glob("*.md"):
            if md_file.stat().st_mtime > index_mtime:
                return True

    return False
