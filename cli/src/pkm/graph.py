"""AST parsing and graph generation for PKM."""

import datetime
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mistletoe
from mistletoe.ast_renderer import ASTRenderer
import networkx as nx
import numpy as np

from pkm.config import VaultConfig
from pkm.frontmatter import parse as parse_note


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine distance between two vectors."""
    try:
        from scipy.spatial.distance import cosine as _scipy_cosine

        return float(_scipy_cosine(a, b))
    except ImportError:
        norm_a = float(np.linalg.norm(a))
        norm_b = float(np.linalg.norm(b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 1.0
        return 1.0 - float(np.dot(a, b)) / (norm_a * norm_b)


def _load_embeddings_from_vector_db(vault: VaultConfig) -> dict[str, np.ndarray]:
    """Load all cached embeddings keyed by note_id. Only returns all-MiniLM-L6-v2 entries."""
    db_path = vault.pkm_dir / "vector.db"
    if not db_path.exists():
        return {}
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT note_id, embedding FROM vector_cache WHERE model = ?",
                ("all-MiniLM-L6-v2",),
            )
            return {
                row[0]: np.frombuffer(row[1], dtype="<f4").copy()
                for row in cursor.fetchall()
            }
    except sqlite3.DatabaseError:
        return {}


def _add_semantic_edges(
    G: nx.DiGraph,
    embeddings: dict[str, np.ndarray],
    threshold: float,
) -> None:
    """Add semantic_similar edges for note pairs with cosine >= threshold.

    Skip pairs already connected by any wikilink edge (either direction).
    Uses numpy matmul on L2-normalized matrix for efficiency.
    """
    note_ids = list(embeddings.keys())
    if len(note_ids) < 2:
        return

    # Build L2-normalized embedding matrix
    matrix = np.stack([embeddings[nid] for nid in note_ids])  # (N, 384)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    matrix_norm = matrix / norms
    sim_matrix = matrix_norm @ matrix_norm.T  # (N, N) cosine similarities

    n = len(note_ids)
    for i in range(n):
        for j in range(i + 1, n):
            sim = float(sim_matrix[i, j])
            if sim < threshold:
                continue
            src = note_ids[i]
            tgt = note_ids[j]
            # Skip if already connected by wikilink in either direction
            fwd_wikilink = (
                G.has_edge(src, tgt) and G.edges[src, tgt].get("type") == "wikilink"
            )
            rev_wikilink = (
                G.has_edge(tgt, src) and G.edges[tgt, src].get("type") == "wikilink"
            )
            if fwd_wikilink or rev_wikilink:
                continue
            edge_attrs = {
                "type": "semantic_similar",
                "source_type": "embedding",
                "confidence": sim,
                "weight": sim,
                "model": "all-MiniLM-L6-v2",
                "extractor_version": "1",
            }
            G.add_edge(src, tgt, **edge_attrs)


def _top_tags_for_members(
    G: nx.DiGraph, members: list[str], top_n: int = 3
) -> list[str]:
    """Return top-N most-frequent tags across cluster members (from has_tag edges)."""
    tag_counter: Counter[str] = Counter()
    for node_id in members:
        for _, tgt, edata in G.out_edges(node_id, data=True):
            if edata.get("type") == "has_tag":
                tag_name = G.nodes[tgt].get("name", tgt.removeprefix("tag:"))
                tag_counter[tag_name] += 1
    return [tag for tag, _ in tag_counter.most_common(top_n)]


def _default(obj: object) -> str:
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def build_enriched_graph(
    vault: VaultConfig, similarity_threshold: float = 0.75
) -> None:
    """Build graph_enriched.json: structural graph + semantic_similar edges + communities.

    Requires vector.db to exist (call pkm index first). Silently skips enrichment
    if graph.json is missing, vector.db is absent, or embeddings are insufficient.
    """
    graph_path = vault.pkm_dir / "graph.json"
    if not graph_path.exists():
        return

    # 1. Load structural graph
    G = nx.node_link_graph(json.loads(graph_path.read_text()))

    # 2. Load embeddings from vector.db
    embeddings = _load_embeddings_from_vector_db(vault)
    if len(embeddings) < 2:
        return

    # 3. Add semantic edges
    _add_semantic_edges(G, embeddings, threshold=similarity_threshold)

    # 3b. Enrich structural edges with confidence=1.0 for louvain weight="confidence"
    for _, _, edata in G.edges(data=True):
        if edata.get("source_type") != "embedding" and "confidence" not in edata:
            edata["confidence"] = 1.0
            edata.setdefault("source_type", "structural")

    # Define output path early — used both for reading prev centroids and writing
    enriched_path = vault.graph_enriched_path

    # 4. Community detection on note-only undirected projection
    note_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "note"]
    G_notes = G.subgraph(note_nodes).to_undirected()
    communities = nx.community.louvain_communities(
        G_notes, seed=42, weight="confidence"
    )
    for community_id, members in enumerate(communities):
        for node_id in members:
            G.nodes[node_id]["community"] = community_id

    # 4b. Compute cluster centroids + drift from previous run
    prev_centroids: list[np.ndarray] = []
    if enriched_path.exists():
        prev_data = json.loads(enriched_path.read_text())
        if prev_data.get("model") == "all-MiniLM-L6-v2":
            prev_centroids = [
                np.array(pc["centroid"], dtype="<f4")
                for pc in prev_data.get("clusters", [])
            ]

    available_prev = list(prev_centroids)

    clusters_meta = []
    for community_id, members in enumerate(communities):
        member_embs = [embeddings[m] for m in members if m in embeddings]
        if not member_embs:
            continue
        centroid = np.mean(member_embs, axis=0)
        prev_centroid = None
        min_drift = float("inf")
        best_idx = -1
        for idx, pv in enumerate(available_prev):
            d = _cosine_distance(centroid, pv)
            if d < min_drift:
                min_drift, prev_centroid, best_idx = d, pv, idx
        if best_idx >= 0:
            available_prev.pop(best_idx)
        is_new = prev_centroid is None
        top_tags = _top_tags_for_members(G, members)
        clusters_meta.append(
            {
                "id": community_id,
                "centroid": centroid.tolist(),
                "prev_centroid": prev_centroid.tolist()
                if prev_centroid is not None
                else None,
                "centroid_drift": round(min_drift, 4) if not is_new else None,
                "is_new": is_new,
                "members": list(members),
                "top_tags": top_tags,
            }
        )

    # 5. Write graph_enriched.json
    data = nx.node_link_data(G)
    data["graph_tier"] = "enriched"
    data["schema_version"] = 1
    data["built_at"] = (
        datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    )
    data["model"] = "all-MiniLM-L6-v2"
    data["clusters"] = clusters_meta
    enriched_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=_default),
        encoding="utf-8",
    )


def find_surprising_connections(vault: VaultConfig, top_n: int = 20) -> list[dict]:
    """Return top-N notes that bridge two different clusters via centroid bridge score.

    bridge_score = 1 / (dist_a + dist_b + abs(dist_a - dist_b))
    Asymmetry penalty rewards equidistance — a note deep in one cluster scores lower than
    a note equidistant from two clusters.

    Returns list of dicts: note_id, bridge_score, cluster_a, cluster_b, dist_a, dist_b, title.
    Returns [] if graph_enriched.json missing or <2 clusters.
    """
    enriched_path = vault.pkm_dir / "graph_enriched.json"
    if not enriched_path.exists():
        return []
    data = json.loads(enriched_path.read_text())
    clusters = data.get("clusters", [])
    if len(clusters) < 2:
        return []

    centroids = {c["id"]: np.array(c["centroid"]) for c in clusters}
    embeddings = _load_embeddings_from_vector_db(vault)

    # Build title lookup from graph nodes
    node_titles: dict[str, str] = {}
    for node in data.get("nodes", []):
        nid = node.get("id", "")
        title = node.get("title") or node.get("id", "")
        node_titles[nid] = title

    results = []
    cluster_ids = list(centroids.keys())
    for note_id, emb in embeddings.items():
        for i, ca_id in enumerate(cluster_ids):
            for cb_id in cluster_ids[i + 1 :]:
                dist_a = _cosine_distance(emb, centroids[ca_id])
                dist_b = _cosine_distance(emb, centroids[cb_id])
                denom = dist_a + dist_b + abs(dist_a - dist_b)
                if denom < 1e-9:
                    continue
                score = 1.0 / denom
                results.append(
                    {
                        "note_id": note_id,
                        "bridge_score": score,
                        "cluster_a": ca_id,
                        "cluster_b": cb_id,
                        "dist_a": dist_a,
                        "dist_b": dist_b,
                        "title": node_titles.get(note_id, note_id),
                    }
                )

    # Deduplicate: keep highest scoring cluster pair per note
    seen: dict[str, dict] = {}
    for r in results:
        key = r["note_id"]
        if key not in seen or r["bridge_score"] > seen[key]["bridge_score"]:
            seen[key] = r
    return sorted(seen.values(), key=lambda x: x["bridge_score"], reverse=True)[:top_n]


@dataclass
class ASTMetadata:
    note_id: str
    path: str
    mtime: float
    links: list[str]
    tags: list[str]
    headings: list[dict[str, Any]]
    plain_text_offsets: list[dict[str, Any]]


def _extract_metadata_from_ast(
    ast_dict: dict[str, Any], current_offset: int = 0
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    links = []
    headings = []
    plain_text_offsets = []

    def traverse(node: dict[str, Any], offset: int) -> int:
        node_type = node.get("type")

        if node_type == "Heading":
            heading_text = ""
            for child in node.get("children", []):
                if child.get("type") == "RawText":
                    heading_text += child.get("content", "")
            headings.append(
                {"level": node.get("level"), "text": heading_text, "offset": offset}
            )

        elif node_type == "RawText":
            content = node.get("content", "")
            plain_text_offsets.append(
                {"text": content, "offset": offset, "length": len(content)}
            )

        if node_type == "RawText":
            content = node.get("content", "")
            for match in re.finditer(r"\[\[(.*?)\]\]", content):
                links.append(match.group(1).split("|")[0])

        current_offset = offset
        for child in node.get("children", []):
            current_offset = traverse(child, current_offset)

        if node_type == "RawText":
            return offset + len(node.get("content", ""))
        return current_offset

    traverse(ast_dict, current_offset)
    return links, headings, plain_text_offsets


def parse_file_ast(file_path: Path, note_id: str) -> ASTMetadata:
    mtime = file_path.stat().st_mtime

    note = parse_note(file_path)
    tags = [str(t) for t in note.tags]

    with ASTRenderer() as renderer:
        doc = mistletoe.Document(note.body)
        ast_dict = json.loads(renderer.render(doc))

    links, headings, plain_text_offsets = _extract_metadata_from_ast(ast_dict)

    return ASTMetadata(
        note_id=note_id,
        path=str(file_path),
        mtime=mtime,
        links=links,
        tags=tags,
        headings=headings,
        plain_text_offsets=plain_text_offsets,
    )


_AST_CACHE_VERSION = 2  # bump to invalidate cache after tag-parsing fixes


class ASTCache:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ast_cache (
                    note_id TEXT PRIMARY KEY,
                    path TEXT,
                    mtime REAL,
                    data TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)
            """)
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'version'"
            ).fetchone()
            if row is None or int(row[0]) != _AST_CACHE_VERSION:
                conn.execute("DELETE FROM ast_cache")
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES ('version', ?)",
                    (str(_AST_CACHE_VERSION),),
                )

    def get(self, note_id: str) -> ASTMetadata | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT path, mtime, data FROM ast_cache WHERE note_id = ?", (note_id,)
            )
            row = cursor.fetchone()
            if row:
                path, mtime, data_json = row
                data = json.loads(data_json)
                return ASTMetadata(
                    note_id=note_id,
                    path=path,
                    mtime=mtime,
                    links=data.get("links", []),
                    tags=data.get("tags", []),
                    headings=data.get("headings", []),
                    plain_text_offsets=data.get("plain_text_offsets", []),
                )
        return None

    def set(self, metadata: ASTMetadata):
        data = {
            "links": metadata.links,
            "tags": metadata.tags,
            "headings": metadata.headings,
            "plain_text_offsets": metadata.plain_text_offsets,
        }
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ast_cache (note_id, path, mtime, data)
                VALUES (?, ?, ?, ?)
            """,
                (metadata.note_id, metadata.path, metadata.mtime, json.dumps(data)),
            )


def build_ast_and_graph(vault: VaultConfig) -> None:
    """Build Incremental AST Cache and networkx graph."""
    db_path = vault.pkm_dir / "ast.db"
    graph_path = vault.pkm_dir / "graph.json"

    cache = ASTCache(db_path)

    md_files: list[Path] = []
    for d in (vault.notes_dir, vault.daily_dir, vault.tags_dir):
        if d.is_dir():
            md_files.extend(sorted(d.glob("*.md")))

    graph = nx.DiGraph()

    for file_path in md_files:
        note = parse_note(file_path)
        note_id = str(note.id)

        mtime = file_path.stat().st_mtime
        cached = cache.get(note_id)

        if cached and cached.mtime >= mtime:
            metadata = cached
        else:
            metadata = parse_file_ast(file_path, note_id)
            cache.set(metadata)

        meta = dict(note.meta)
        if not meta.get("description") and note.body:
            body_text = note.body.strip()
            if body_text:
                meta["description"] = body_text[:200].replace("\n", " ").strip() + (
                    "..." if len(body_text) > 200 else ""
                )

        graph.add_node(
            note_id,
            type="note",
            title=note.title,
            path=str(file_path),
            meta=meta,
        )

        for tag in metadata.tags:
            tag_id = f"tag:{tag}"
            graph.add_node(tag_id, type="tag", name=tag)
            graph.add_edge(note_id, tag_id, type="has_tag")

        # Tag notes (files in tags_dir) bridge to their tag node
        if (
            vault.tags_dir.is_dir()
            and file_path.parent.resolve() == vault.tags_dir.resolve()
        ):
            tag_name = file_path.stem
            tag_id = f"tag:{tag_name}"
            graph.add_node(tag_id, type="tag", name=tag_name)
            graph.add_edge(note_id, tag_id, type="tag_note")

        for link in metadata.links:
            graph.add_node(link, type="note_or_unresolved", title=link)
            graph.add_edge(note_id, link, type="wikilink")

    # Post-process: link tag notes directly to all notes that use that tag.
    # This makes get_note_neighbors(tag_note) return tagged notes as direct neighbors.
    if vault.tags_dir.is_dir():
        for file_path in md_files:
            if file_path.parent.resolve() != vault.tags_dir.resolve():
                continue
            tag_note_id = str(parse_note(file_path).id)
            tag_hub_id = f"tag:{file_path.stem}"
            if not graph.has_node(tag_hub_id):
                continue
            for tagged_id in list(graph.predecessors(tag_hub_id)):
                node_type = graph.nodes.get(tagged_id, {}).get("type", "")
                if (
                    node_type in ("note", "note_or_unresolved")
                    and tagged_id != tag_note_id
                ):
                    graph.add_edge(tag_note_id, tagged_id, type="tagged_by")
                    graph.add_edge(tagged_id, tag_note_id, type="uses_tag_note")

    graph_data = nx.node_link_data(graph)
    graph_path.write_text(
        json.dumps(graph_data, ensure_ascii=False, indent=2, default=_default),
        encoding="utf-8",
    )
