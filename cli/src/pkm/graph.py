"""AST parsing and graph generation for PKM."""

import datetime
import json
import logging
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

from pkm.config import VaultConfig, load_config
from pkm.frontmatter import parse as parse_note
from pkm.note_summary import note_description
from pkm.search_engine import atomic_write_json
from pkm.relations import (
    RelationMarker,
    collect_relation_state,
    parse_relation_markers,
    write_relation_outputs,
)
from pkm.wikilinks import extract_links

logger = logging.getLogger(__name__)

SEMANTIC_SCORING_DEFAULTS = {
    "candidate_threshold": 0.7325,
    "score_threshold": 0.5952,
    "mutual_top_k": 40,
    "shared_neighbor_k": 20,
    "local_neighbor_k": 15,
    "weight_cosine": 0.0,
    "weight_rank": 0.0652,
    "weight_csls": 0.0922,
    "weight_shared_neighbor": 0.3244,
    "weight_local_z": 0.5182,
    "min_description_chars": 20,
    "finance_cross_domain_mode": "block",
    "finance_cross_domain_penalty": 0.1943,
}


@dataclass(frozen=True)
class SemanticScoringConfig:
    candidate_threshold: float = SEMANTIC_SCORING_DEFAULTS["candidate_threshold"]
    score_threshold: float = SEMANTIC_SCORING_DEFAULTS["score_threshold"]
    mutual_top_k: int = SEMANTIC_SCORING_DEFAULTS["mutual_top_k"]
    shared_neighbor_k: int = SEMANTIC_SCORING_DEFAULTS["shared_neighbor_k"]
    local_neighbor_k: int = SEMANTIC_SCORING_DEFAULTS["local_neighbor_k"]
    weight_cosine: float = SEMANTIC_SCORING_DEFAULTS["weight_cosine"]
    weight_rank: float = SEMANTIC_SCORING_DEFAULTS["weight_rank"]
    weight_csls: float = SEMANTIC_SCORING_DEFAULTS["weight_csls"]
    weight_shared_neighbor: float = SEMANTIC_SCORING_DEFAULTS[
        "weight_shared_neighbor"
    ]
    weight_local_z: float = SEMANTIC_SCORING_DEFAULTS["weight_local_z"]
    min_description_chars: int = SEMANTIC_SCORING_DEFAULTS["min_description_chars"]
    finance_cross_domain_mode: str = SEMANTIC_SCORING_DEFAULTS[
        "finance_cross_domain_mode"
    ]
    finance_cross_domain_penalty: float = SEMANTIC_SCORING_DEFAULTS[
        "finance_cross_domain_penalty"
    ]


def _float_config(defaults: dict[str, Any], key: str, fallback: float) -> float:
    value = defaults.get(key, fallback)
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _int_config(defaults: dict[str, Any], key: str, fallback: int) -> int:
    value = defaults.get(key, fallback)
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def semantic_scoring_config_from_defaults(
    defaults: dict[str, Any] | None = None,
) -> SemanticScoringConfig:
    defaults = defaults or {}
    return SemanticScoringConfig(
        candidate_threshold=_float_config(
            defaults,
            "graph-semantic-candidate-threshold",
            _float_config(
                defaults,
                "graph-similarity-threshold",
                SEMANTIC_SCORING_DEFAULTS["candidate_threshold"],
            ),
        ),
        score_threshold=_float_config(
            defaults,
            "graph-semantic-score-threshold",
            SEMANTIC_SCORING_DEFAULTS["score_threshold"],
        ),
        mutual_top_k=max(
            1,
            _int_config(
                defaults,
                "graph-semantic-mutual-top-k",
                SEMANTIC_SCORING_DEFAULTS["mutual_top_k"],
            ),
        ),
        shared_neighbor_k=max(
            1,
            _int_config(
                defaults,
                "graph-semantic-shared-neighbor-k",
                SEMANTIC_SCORING_DEFAULTS["shared_neighbor_k"],
            ),
        ),
        local_neighbor_k=max(
            1,
            _int_config(
                defaults,
                "graph-semantic-local-neighbor-k",
                SEMANTIC_SCORING_DEFAULTS["local_neighbor_k"],
            ),
        ),
        weight_cosine=_float_config(
            defaults,
            "graph-semantic-weight-cosine",
            SEMANTIC_SCORING_DEFAULTS["weight_cosine"],
        ),
        weight_rank=_float_config(
            defaults,
            "graph-semantic-weight-rank",
            SEMANTIC_SCORING_DEFAULTS["weight_rank"],
        ),
        weight_csls=_float_config(
            defaults,
            "graph-semantic-weight-csls",
            SEMANTIC_SCORING_DEFAULTS["weight_csls"],
        ),
        weight_shared_neighbor=_float_config(
            defaults,
            "graph-semantic-weight-shared-neighbor",
            SEMANTIC_SCORING_DEFAULTS["weight_shared_neighbor"],
        ),
        weight_local_z=_float_config(
            defaults,
            "graph-semantic-weight-local-z",
            SEMANTIC_SCORING_DEFAULTS["weight_local_z"],
        ),
        min_description_chars=max(
            0,
            _int_config(
                defaults,
                "graph-semantic-min-description-chars",
                SEMANTIC_SCORING_DEFAULTS["min_description_chars"],
            ),
        ),
        finance_cross_domain_mode=str(
            defaults.get(
                "graph-semantic-finance-cross-domain-mode",
                SEMANTIC_SCORING_DEFAULTS["finance_cross_domain_mode"],
            )
        ),
        finance_cross_domain_penalty=_float_config(
            defaults,
            "graph-semantic-finance-cross-domain-penalty",
            SEMANTIC_SCORING_DEFAULTS["finance_cross_domain_penalty"],
        ),
    )


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


def _node_tags(G: nx.DiGraph, node_id: str) -> set[str]:
    meta = G.nodes.get(node_id, {}).get("meta", {})
    if not isinstance(meta, dict):
        return set()
    tags = meta.get("tags", [])
    if not isinstance(tags, list):
        return set()
    return {str(tag) for tag in tags if tag is not None and str(tag) != "None"}


def _node_title(G: nx.DiGraph, node_id: str) -> str:
    node = G.nodes.get(node_id, {})
    return str(node.get("title") or node.get("id") or node_id)


def _node_description(G: nx.DiGraph, node_id: str) -> str:
    meta = G.nodes.get(node_id, {}).get("meta", {})
    if isinstance(meta, dict):
        return str(meta.get("description") or "")
    return ""


def _is_finance_node(G: nx.DiGraph, node_id: str) -> bool:
    title = _node_title(G, node_id)
    tags = _node_tags(G, node_id)
    finance_tags = {"주식분석", "딥리서치", "주도주", "투자일지", "my-invest", "매크로", "트렌드"}
    return (
        bool(tags & finance_tags)
        or "[주식분석]" in title
        or "stock" in title.lower()
        or "investment" in title.lower()
    )


def _add_semantic_edges(
    G: nx.DiGraph,
    embeddings: dict[str, np.ndarray],
    threshold: float,
    scoring_config: SemanticScoringConfig | None = None,
    mutual_top_k: int = 20,
    shared_neighbor_k: int = 20,
) -> None:
    """Add semantic_similar edges for reciprocal nearest-neighbor note pairs.

    Skip pairs already connected by any wikilink edge (either direction).
    Uses numpy matmul on L2-normalized matrix for efficiency. Cosine still forms
    the candidate set, but reciprocal rank and local-neighborhood diagnostics
    keep broad embedding hubs from becoming overconfident graph edges.
    """
    note_ids = list(embeddings.keys())
    if len(note_ids) < 2:
        return
    if scoring_config is None:
        scoring_config = SemanticScoringConfig(
            candidate_threshold=threshold,
            score_threshold=threshold,
            mutual_top_k=mutual_top_k,
            shared_neighbor_k=shared_neighbor_k,
        )

    # Build L2-normalized embedding matrix
    matrix = np.stack([embeddings[nid] for nid in note_ids])  # (N, 384)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    matrix_norm = matrix / norms
    sim_matrix = matrix_norm @ matrix_norm.T  # (N, N) cosine similarities

    n = len(note_ids)
    neighbor_limit = max(1, min(scoring_config.mutual_top_k, n - 1))
    shared_limit = max(1, min(scoring_config.shared_neighbor_k, n - 1))
    local_limit = max(
        neighbor_limit,
        shared_limit,
        min(scoring_config.local_neighbor_k, n - 1),
    )

    ranking_matrix = sim_matrix.copy()
    np.fill_diagonal(ranking_matrix, -np.inf)
    neighbor_order = np.argsort(-ranking_matrix, axis=1)

    ranks = np.zeros((n, n), dtype=np.int32)
    for row_idx in range(n):
        for rank, neighbor_idx in enumerate(neighbor_order[row_idx], start=1):
            if neighbor_idx == row_idx:
                continue
            ranks[row_idx, neighbor_idx] = rank

    top_sets = [
        set(int(idx) for idx in neighbor_order[row_idx][:shared_limit])
        for row_idx in range(n)
    ]
    local_means = np.zeros(n, dtype=float)
    local_stds = np.ones(n, dtype=float)
    for row_idx in range(n):
        local_neighbors = neighbor_order[row_idx][:local_limit]
        local_scores = ranking_matrix[row_idx, local_neighbors]
        finite_scores = local_scores[np.isfinite(local_scores)]
        if finite_scores.size == 0:
            continue
        local_means[row_idx] = float(np.mean(finite_scores))
        std = float(np.std(finite_scores))
        local_stds[row_idx] = std if std > 1e-9 else 1.0

    for i in range(n):
        for j in range(i + 1, n):
            sim = float(sim_matrix[i, j])
            if sim < scoring_config.candidate_threshold:
                continue
            source_rank = int(ranks[i, j])
            target_rank = int(ranks[j, i])
            if source_rank > neighbor_limit or target_rank > neighbor_limit:
                continue
            src = note_ids[i]
            tgt = note_ids[j]
            if scoring_config.min_description_chars > 0:
                if (
                    len(_node_description(G, src)) < scoring_config.min_description_chars
                    or len(_node_description(G, tgt))
                    < scoring_config.min_description_chars
                ):
                    continue
            # Skip if already connected by wikilink in either direction
            fwd_wikilink = (
                G.has_edge(src, tgt) and G.edges[src, tgt].get("type") == "wikilink"
            )
            rev_wikilink = (
                G.has_edge(tgt, src) and G.edges[tgt, src].get("type") == "wikilink"
            )
            if fwd_wikilink or rev_wikilink:
                continue

            source_top = top_sets[i]
            target_top = top_sets[j]
            shared_neighbors = source_top & target_top
            neighbor_union = source_top | target_top
            shared_neighbor_score = (
                len(shared_neighbors) / len(neighbor_union) if neighbor_union else 0.0
            )
            csls_score = float(2 * sim - local_means[i] - local_means[j])
            source_z = (sim - local_means[i]) / local_stds[i]
            target_z = (sim - local_means[j]) / local_stds[j]
            local_z_score = float(min(source_z, target_z))
            reciprocal_rank_score = float(1 / np.sqrt(source_rank * target_rank))
            csls_component = max(0.0, min(1.0, (csls_score + 1.0) / 2.0))
            z_component = max(0.0, min(1.0, (local_z_score + 1.0) / 2.0))
            semantic_score = (
                scoring_config.weight_cosine * sim
                + scoring_config.weight_rank * reciprocal_rank_score
                + scoring_config.weight_csls * csls_component
                + scoring_config.weight_shared_neighbor * shared_neighbor_score
                + scoring_config.weight_local_z * z_component
            )
            src_finance = _is_finance_node(G, src)
            tgt_finance = _is_finance_node(G, tgt)
            if src_finance != tgt_finance:
                mode = scoring_config.finance_cross_domain_mode.lower()
                if mode == "block":
                    continue
                if mode == "penalize":
                    semantic_score -= scoring_config.finance_cross_domain_penalty
            semantic_score = max(0.0, min(1.0, float(semantic_score)))
            if semantic_score < scoring_config.score_threshold:
                continue
            edge_attrs = {
                "type": "semantic_similar",
                "source_type": "embedding",
                "confidence": semantic_score,
                "weight": semantic_score,
                "semantic_score": semantic_score,
                "cosine_similarity": sim,
                "source_rank": source_rank,
                "target_rank": target_rank,
                "reciprocal_rank_score": reciprocal_rank_score,
                "csls_score": csls_score,
                "shared_neighbor_score": shared_neighbor_score,
                "local_z_score": local_z_score,
                "model": "all-MiniLM-L6-v2",
                "extractor_version": "2",
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
    vault: VaultConfig,
    similarity_threshold: float | None = None,
    scoring_config: SemanticScoringConfig | None = None,
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
    if scoring_config is None:
        scoring_config = semantic_scoring_config_from_defaults(
            load_config().get("defaults", {})
        )
    if similarity_threshold is not None:
        scoring_config = SemanticScoringConfig(
            **{
                **scoring_config.__dict__,
                "candidate_threshold": similarity_threshold,
                "score_threshold": similarity_threshold,
            }
        )
    _add_semantic_edges(
        G,
        embeddings,
        threshold=scoring_config.candidate_threshold,
        scoring_config=scoring_config,
    )

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
    atomic_write_json(enriched_path, data, default=_default, indent=2)


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
    relations: list[RelationMarker]


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
            links.extend(extract_links(content))

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
    relations = parse_relation_markers(note.body, source_path=str(file_path)).markers

    return ASTMetadata(
        note_id=note_id,
        path=str(file_path),
        mtime=mtime,
        links=links,
        tags=tags,
        headings=headings,
        plain_text_offsets=plain_text_offsets,
        relations=relations,
    )


_AST_CACHE_VERSION = 4  # bump to invalidate cache after relation metadata support


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
                    relations=[
                        RelationMarker(**item) for item in data.get("relations", [])
                    ],
                )
        return None

    def set(self, metadata: ASTMetadata):
        data = {
            "links": metadata.links,
            "tags": metadata.tags,
            "headings": metadata.headings,
            "plain_text_offsets": metadata.plain_text_offsets,
            "relations": [item.__dict__ for item in metadata.relations],
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
        try:
            note = parse_note(file_path)
        except Exception as exc:
            logger.warning(
                "Skipping malformed note in graph build: %s (%s)", file_path, exc
            )
            continue
        note_id = str(note.id)

        mtime = file_path.stat().st_mtime
        cached = cache.get(note_id)

        if cached and cached.mtime >= mtime:
            metadata = cached
        else:
            try:
                metadata = parse_file_ast(file_path, note_id)
            except Exception as exc:
                logger.warning(
                    "Skipping note after AST parse failure: %s (%s)", file_path, exc
                )
                continue
            cache.set(metadata)

        meta = dict(note.meta)
        description = note_description(meta, note.body)
        if description:
            meta["description"] = description

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
            if not graph.has_node(link):
                graph.add_node(link, type="note_or_unresolved", title=link)
            graph.add_edge(note_id, link, type="wikilink")

        if file_path.parent.resolve() == vault.notes_dir.resolve():
            source_path = file_path.relative_to(vault.path).as_posix()
            for relation in metadata.relations:
                if not graph.has_node(relation.target):
                    graph.add_node(
                        relation.target,
                        type="note_or_unresolved",
                        title=relation.target,
                    )
                if not graph.has_edge(note_id, relation.target):
                    graph.add_edge(note_id, relation.target, type="wikilink")
                edge = graph.edges[note_id, relation.target]
                edge.setdefault("relations", []).append(
                    relation.to_edge_metadata(source_path)
                )

    # Post-process: link tag notes directly to all notes that use that tag.
    # This makes get_note_neighbors(tag_note) return tagged notes as direct neighbors.
    if vault.tags_dir.is_dir():
        for file_path in md_files:
            if file_path.parent.resolve() != vault.tags_dir.resolve():
                continue
            try:
                tag_note_id = str(parse_note(file_path).id)
            except Exception as exc:
                logger.warning(
                    "Skipping malformed tag note in graph post-processing: %s (%s)",
                    file_path,
                    exc,
                )
                continue
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
    atomic_write_json(graph_path, graph_data, default=_default, indent=2)
    write_relation_outputs(vault, collect_relation_state(vault))
