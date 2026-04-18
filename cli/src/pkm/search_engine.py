"""Semantic search engine for PKM vaults using sentence-transformers."""

from __future__ import annotations

import json
import re as _re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import click

from pkm.config import VaultConfig
from pkm.frontmatter import parse
from pkm.wikilinks import count_backlinks
from pkm._memory_types import CURRENT_SCHEMA_VERSION, IMPORTANCE_DEFAULT


from typing import Any

_MODEL_CACHE: dict[str, Any] = {}


def _require_transformers(model_name: str):
    """Lazily import and return a SentenceTransformer, raising a friendly error if missing."""
    if model_name in _MODEL_CACHE:
        return _MODEL_CACHE[model_name]
    try:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
    except ImportError:
        raise click.ClickException(
            "sentence-transformers is not installed. Run: pkm setup"
        )
    model = SentenceTransformer(model_name)
    _MODEL_CACHE[model_name] = model
    return model


@dataclass
class IndexEntry:
    note_id: str
    path: str
    embedding: list[float]
    backlink_count: int
    tags: list[str]
    title: str
    # Schema v2 fields
    memory_type: str | None = None
    importance: float = IMPORTANCE_DEFAULT
    created_at: str | None = None  # ISO 8601 datetime string


@dataclass
class VectorIndex:
    model: str
    created_at: str
    entries: list[IndexEntry] = field(default_factory=list)
    schema_version: int = 1


@dataclass
class SearchResult:
    note_id: str
    title: str
    score: float
    backlink_count: int
    tags: list[str]
    rank: int
    memory_type: str | None = None
    importance: float = IMPORTANCE_DEFAULT
    path: str = ""
    graph_context: dict | None = None


def _extract_created_at(
    note_path: Path, frontmatter_data: dict[str, Any]
) -> str | None:
    """Extract created_at from frontmatter, falling back to filename date pattern."""
    if ca := frontmatter_data.get("created_at"):
        return str(ca)
    # Try YYYY-MM-DD from filename
    match = _re.match(r"(\d{4}-\d{2}-\d{2})", note_path.stem)
    if match:
        return f"{match.group(1)}T00:00:00+00:00"
    return None


def build_index(
    vault: VaultConfig, model_name: str = "all-MiniLM-L6-v2"
) -> VectorIndex:
    """Build a vector index for all notes and daily notes in the vault."""
    from pkm.graph import build_ast_and_graph

    build_ast_and_graph(vault)

    model = _require_transformers(model_name)
    backlink_counts = count_backlinks(vault)

    md_files: list[Path] = []
    for d in (vault.notes_dir, vault.daily_dir, vault.tags_dir):
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
                memory_type=note.meta.get("memory_type"),
                importance=float(note.meta.get("importance", IMPORTANCE_DEFAULT)),
                created_at=_extract_created_at(note.path, note.meta),
            )
        )

    index = VectorIndex(
        model=model_name,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        entries=entries,
        schema_version=CURRENT_SCHEMA_VERSION,
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
                "schema_version": index.schema_version,
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


def search(
    query: str,
    index: VectorIndex,
    top_n: int = 10,
    model_name: str = "all-MiniLM-L6-v2",
    memory_type_filter: str | None = None,
    recency_weight: float = 0.0,
    min_importance: float = 1.0,
) -> list[SearchResult]:
    """Search the index for notes semantically similar to the query."""
    import numpy as np
    from datetime import datetime, timezone

    model = _require_transformers(model_name)
    query_emb = model.encode([query], show_progress_bar=False)[0]

    now = datetime.now(timezone.utc)

    scored: list[tuple[float, IndexEntry]] = []
    for entry in index.entries:
        # Filter by memory_type
        if memory_type_filter and entry.memory_type != memory_type_filter:
            continue
        # Filter by importance
        if entry.importance < min_importance:
            continue

        emb = np.array(entry.embedding, dtype=float)
        q = np.array(query_emb, dtype=float)
        norm_e = np.linalg.norm(emb)
        norm_q = np.linalg.norm(q)
        if norm_e == 0 or norm_q == 0:
            cos_sim = 0.0
        else:
            cos_sim = float(np.dot(q, emb) / (norm_q * norm_e))

        # Compute recency score
        recency_score = 1.0
        if recency_weight > 0 and entry.created_at:
            try:
                created = datetime.fromisoformat(entry.created_at)
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                hours_ago = (now - created).total_seconds() / 3600
                recency_score = 0.995**hours_ago
            except ValueError:
                recency_score = 0.5  # fallback for unparseable dates

        importance_norm = entry.importance / 10.0
        final_score = (
            1 - recency_weight
        ) * cos_sim + recency_weight * recency_score * importance_norm

        scored.append((final_score, entry))

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
                memory_type=entry.memory_type,
                importance=entry.importance,
                path=entry.path,
            )
        )

    return results


def find_similar(
    content: str,
    index: VectorIndex,
    threshold: float = 0.85,
    top_n: int = 3,
    model_name: str = "all-MiniLM-L6-v2",
) -> list[SearchResult]:
    """Find notes semantically similar to content at or above threshold.

    Returns empty list on any failure — never raises exceptions.
    """
    try:
        import numpy as np

        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        except ImportError:
            return []

        if model_name not in _MODEL_CACHE:
            _MODEL_CACHE[model_name] = SentenceTransformer(model_name)
        model = _MODEL_CACHE[model_name]
        query_emb = model.encode([content], show_progress_bar=False)[0]  # type: ignore[union-attr]

        scored: list[tuple[float, IndexEntry]] = []
        for entry in index.entries:
            emb = np.array(entry.embedding, dtype=float)
            q = np.array(query_emb, dtype=float)
            norm_e = np.linalg.norm(emb)
            norm_q = np.linalg.norm(q)
            if norm_e == 0 or norm_q == 0:
                continue
            cos_sim = float(np.dot(q, emb) / (norm_q * norm_e))
            if cos_sim >= threshold:
                scored.append((cos_sim, entry))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[SearchResult] = []
        for rank, (score, entry) in enumerate(scored[:top_n], 1):
            results.append(
                SearchResult(
                    note_id=entry.note_id,
                    title=entry.title,
                    score=score,
                    backlink_count=entry.backlink_count,
                    tags=entry.tags,
                    rank=rank,
                    memory_type=entry.memory_type,
                    importance=entry.importance,
                    path=entry.path,
                )
            )
        return results
    except Exception:
        return []


def search_via_daemon(
    query: str,
    vault: VaultConfig,
    top_n: int = 10,
    min_importance: float = 1.0,
    memory_type_filter: str | None = None,
    recency_weight: float = 0.0,
) -> list[SearchResult] | None:
    """Attempt to search via the background ML daemon. Returns None if daemon is unavailable."""
    import socket
    import subprocess
    import sys

    index_path = vault.pkm_dir / "index.json"
    if not index_path.exists():
        return None

    index_mtime = index_path.stat().st_mtime
    sock_path = Path.home() / ".config" / "pkm" / "daemon.sock"

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            sock.connect(str(sock_path))
            sock.settimeout(1.5)

            req = {
                "query": query,
                "vault_name": vault.name,
                "top_n": top_n,
                "min_importance": min_importance,
                "memory_type_filter": memory_type_filter,
                "recency_weight": recency_weight,
            }
            sock.sendall(json.dumps(req).encode("utf-8") + b"\n")

            f = sock.makefile("r", encoding="utf-8")
            resp_line = f.readline()
            if not resp_line:
                return None

            data = json.loads(resp_line)
            if "error" in data:
                return None

            return [SearchResult(**res) for res in data]

    except (FileNotFoundError, ConnectionRefusedError, socket.timeout):
        daemon_dir = Path.home() / ".config" / "pkm"
        daemon_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(
                [sys.executable, "-m", "pkm.daemon"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass
        return None
    except Exception:
        return None


def update_index_via_daemon(vault: VaultConfig) -> bool:
    """Attempt to update index via the background ML daemon. Returns True if successful."""
    import socket
    import subprocess
    import sys

    sock_path = Path.home() / ".config" / "pkm" / "daemon.sock"

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            sock.connect(str(sock_path))
            sock.settimeout(10.0)

            req = {
                "action": "update_index",
                "vault_name": vault.name,
            }
            sock.sendall(json.dumps(req).encode("utf-8") + b"\n")

            f = sock.makefile("r", encoding="utf-8")
            resp_line = f.readline()
            if not resp_line:
                return False

            data = json.loads(resp_line)
            return data.get("status") == "ok"

    except (FileNotFoundError, ConnectionRefusedError, socket.timeout):
        daemon_dir = Path.home() / ".config" / "pkm"
        daemon_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(
                [sys.executable, "-m", "pkm.daemon"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass
        return False
    except Exception:
        return False


def is_index_stale(vault: VaultConfig) -> bool:
    """Return True if any .md file is newer than the index, or schema version mismatch."""
    index_path = vault.pkm_dir / "index.json"
    if not index_path.exists():
        return True

    # Check schema version
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        if data.get("schema_version", 1) != CURRENT_SCHEMA_VERSION:
            return True
    except (json.JSONDecodeError, KeyError):
        return True

    index_mtime = index_path.stat().st_mtime

    for d in (vault.notes_dir, vault.daily_dir, vault.tags_dir):
        if not d.is_dir():
            continue
        for md_file in d.glob("*.md"):
            if md_file.stat().st_mtime > index_mtime:
                return True

    return False


def get_graph_context_via_daemon(note_id: str, vault, depth: int = 1) -> dict | None:
    import socket
    import json
    from pathlib import Path
    
    graph_path = vault.pkm_dir / "graph.json"
    if not graph_path.exists():
        return None
        
    graph_mtime = graph_path.stat().st_mtime
    sock_path = Path.home() / ".config" / "pkm" / "daemon.sock"
    
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            sock.connect(str(sock_path))
            sock.settimeout(1.5)
            
            req = {
                "action": "get_graph_context",
                "note_id": note_id,
                "depth": depth,
                "vault_name": vault.name,
            }
            sock.sendall(json.dumps(req).encode("utf-8") + b"\n")
            
            f = sock.makefile("r", encoding="utf-8")
            resp_line = f.readline()
            if not resp_line:
                return None
                
            data = json.loads(resp_line)
            if "error" in data:
                return None
                
            return data
    except Exception:
        return None
