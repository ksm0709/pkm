import json
import os
import re
from pathlib import Path
from tiny_agent.tools import tool
from pkm.config import VaultConfig
from pkm.search_engine import (
    search_via_daemon,
    load_index,
    search as search_fn,
    get_graph_context_via_daemon,
)


def _get_vault(vault_dir: str) -> VaultConfig:
    return VaultConfig(name=Path(vault_dir).name, path=Path(vault_dir))


def _slugify(title: str) -> str:
    """Convert a title to a filename-safe slug."""
    s = title.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-") or "hub-note"


@tool()
def semantic_search(
    query: str,
    top: int = 5,
    memory_type: str | None = None,
    min_importance: float = 1.0,
) -> str:
    """Search vault notes semantically.

    Args:
        query: The search query.
        top: Number of results to return.
        memory_type: Optional filter by memory type ('episodic', 'semantic', 'procedural').
        min_importance: Minimum importance score (1.0 to 10.0).
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
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


@tool()
def get_graph_context(note_id: str, depth: int = 1, tier: str = "enriched") -> str:
    """Get graph connections for a note.

    tier='enriched' (default) includes semantic_similar edges and community info
    from graph_enriched.json when available. Falls back to structural graph.json.
    tier='structural' forces structural (wikilink + has_tag only).

    Args:
        note_id: The ID of the note to query.
        depth: The traversal depth (default 1).
        tier: Graph tier to use ('enriched' or 'structural', default 'enriched').
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)

    try:
        context = get_graph_context_via_daemon(note_id, vault, depth, tier=tier)
        if not context:
            return f"No graph context found for '{note_id}' (Daemon may be down or note missing)."

        return json.dumps(context, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error fetching graph context: {str(e)}"


@tool()
def find_surprising_connections(top_n: int = 20) -> str:
    """Find notes that semantically bridge two different topic clusters (hidden cross-cluster links).

    Use this when you want to discover non-obvious connections between different areas of the vault —
    notes whose embeddings sit equidistant between two cluster centroids, suggesting they could
    link topics that haven't been explicitly connected yet.

    WHY: Notes deep inside one cluster score lower than equidistant bridge notes due to the
    asymmetry penalty (|dist_a - dist_b| term). A high bridge_score means the note truly sits
    between two worlds, not just close to one.

    Call this before add_wikilink() to identify which connections are worth making explicit.
    Requires `pkm index` to have been run to build the enriched graph.

    Args:
        top_n: Number of top bridge notes to return (default 20).
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)
    try:
        from pkm.graph import find_surprising_connections as _find

        results = _find(vault, top_n=top_n)
        if not results:
            return "No surprising connections found (run `pkm index` first to build enriched graph)."
        lines = []
        for r in results:
            lines.append(
                f"[[{r['title']}]] bridges cluster {r['cluster_a']}\u2194{r['cluster_b']}"
                f" (score={r['bridge_score']:.3f}, dist_a={r['dist_a']:.2f}, dist_b={r['dist_b']:.2f})"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error finding surprising connections: {str(e)}"


@tool()
def list_clusters() -> str:
    """List all topic clusters discovered in the vault with membership stats and hub notes.

    Use this to understand the current thematic structure of the vault — how many clusters exist,
    how big they are, whether any clusters are new or have shifted (centroid_drift), and which
    index notes serve as hubs. Call this before create_hub_note() to see which clusters lack hubs,
    and before find_surprising_connections() to orient yourself in the cluster landscape.

    WHY: Clusters are detected via Louvain community detection on the semantic graph. centroid_drift
    > 0.2 means the cluster's topic has shifted since the last index run — its hub note may be stale.
    is_new=yes means a brand-new cluster this run — a candidate for create_hub_note().

    Requires `pkm index` to have been run to build the enriched graph.

    Returns JSON: {"clusters": [{id, member_count, top_tags, hub_note, centroid_drift, is_new}, ...]}
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)
    try:
        enriched_path = vault.pkm_dir / "graph_enriched.json"
        if not enriched_path.exists():
            return "No enriched graph found (run `pkm index` first)."
        data = json.loads(enriched_path.read_text())
        clusters = data.get("clusters", [])
        if not clusters:
            return "No clusters found in enriched graph."

        # Find hub notes: index notes whose embeddings are closest to each cluster centroid
        import numpy as np
        from pkm.graph import _load_embeddings_from_vector_db, _cosine_distance
        from pkm.frontmatter import parse as parse_note

        embeddings = _load_embeddings_from_vector_db(vault)

        # Collect index notes that also have embeddings
        index_notes: list[tuple[str, str, np.ndarray]] = []  # (note_id, title, embedding)
        notes_dir = vault.notes_dir
        if notes_dir.is_dir():
            for md_file in sorted(notes_dir.glob("*.md")):
                try:
                    note = parse_note(md_file)
                    if note.meta.get("type") == "index":
                        note_id = str(note.id)
                        if note_id in embeddings:
                            index_notes.append((note_id, note.title, embeddings[note_id]))
                except Exception:
                    pass

        # Build centroids lookup
        centroids = {}
        for c in clusters:
            cid = c.get("id")
            raw = c.get("centroid")
            if cid is not None and raw is not None:
                centroids[cid] = np.array(raw, dtype="<f4")

        HUB_THRESHOLD = 0.3

        cluster_list = []
        for c in clusters:
            cid = c.get("id")
            member_count = len(c.get("members", []))
            top_tags = c.get("top_tags", [])
            drift = c.get("centroid_drift")
            is_new = bool(c.get("is_new"))

            hub_note = None
            if index_notes and cid in centroids:
                centroid = centroids[cid]
                best_dist = float("inf")
                best_title = None
                for _nid, title, emb in index_notes:
                    d = _cosine_distance(emb, centroid)
                    if d < best_dist:
                        best_dist, best_title = d, title
                if best_dist < HUB_THRESHOLD:
                    hub_note = best_title

            cluster_list.append(
                {
                    "id": cid,
                    "member_count": member_count,
                    "top_tags": top_tags,
                    "hub_note": hub_note,
                    "centroid_drift": drift,
                    "is_new": is_new,
                }
            )

        payload = {"clusters": cluster_list}
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error listing clusters: {str(e)}"


@tool()
def list_god_nodes(top_n: int = 10) -> str:
    """List the most connected notes in the vault by combined degree + betweenness centrality.

    Use this to identify hub notes that hold the knowledge graph together — removing them would
    fragment large parts of the graph. Useful for understanding vault architecture, finding notes
    that deserve richer content, and spotting over-connected notes that may need splitting.

    WHY: God nodes combine high degree centrality (many direct connections) and high betweenness
    centrality (lies on many shortest paths between other notes). A note scoring high on both is
    a true structural hub, not just a popular reference.

    Loads graph_enriched.json if available, falls back to graph.json.
    Requires `pkm index` to have been run.

    Args:
        top_n: Number of top hub notes to return (default 10).
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)
    try:
        import networkx as nx

        enriched_path = vault.pkm_dir / "graph_enriched.json"
        graph_path = vault.pkm_dir / "graph.json"
        if enriched_path.exists():
            data = json.loads(enriched_path.read_text())
        elif graph_path.exists():
            data = json.loads(graph_path.read_text())
        else:
            return "No graph found (run `pkm index` first)."

        G = nx.node_link_graph(data)
        note_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "note"]
        if not note_nodes:
            return "No note nodes found in graph."
        G_notes = G.subgraph(note_nodes).to_undirected()
        deg = nx.degree_centrality(G_notes)
        bet = nx.betweenness_centrality(G_notes)
        scored = [(nid, deg.get(nid, 0.0) + bet.get(nid, 0.0)) for nid in note_nodes]
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:top_n]
        lines = [f"{'note_id':<40} {'centrality':<12}"]
        lines.append("-" * 54)
        for nid, score in top:
            node_data = G.nodes[nid]
            title = node_data.get("title", nid)
            lines.append(f"{title:<40} {score:.4f}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing god nodes: {str(e)}"


@tool()
def create_hub_note(cluster_index: int, title: str, description: str) -> str:
    """Create an index note that serves as the hub for a topic cluster.

    Use this after list_clusters() identifies a cluster without a hub note and you've
    read enough member notes to give the cluster a coherent name and description.
    The hub note links all cluster members via a '## Members' wikilink list and is
    tagged with the cluster's top_tags, making it discoverable in the vault's graph view.

    WHY: Clusters without hub notes are invisible in Obsidian's graph view — they exist as
    semantic groupings but have no named entry point. Hub notes make clusters navigable,
    provide context for why members are related, and give the agent a reference point for
    future cluster drift reviews.

    Requires `pkm index` to have been run to build the enriched graph.

    Args:
        cluster_index: The cluster ID from list_clusters() output.
        title: Descriptive title for the hub note (becomes the note's title and filename).
        description: A paragraph explaining what this cluster is about and why these notes belong together.
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)
    try:
        enriched_path = vault.pkm_dir / "graph_enriched.json"
        if not enriched_path.exists():
            return "No enriched graph found (run `pkm index` first)."
        data = json.loads(enriched_path.read_text())
        clusters = data.get("clusters", [])
        cluster = next((c for c in clusters if c.get("id") == cluster_index), None)
        if cluster is None:
            return f"Cluster {cluster_index} not found. Run list_clusters() to see available clusters."

        members = cluster.get("members", [])
        top_tags = cluster.get("top_tags", [])

        member_lines = "\n".join(f"- [[{m}]]" for m in sorted(members))
        tags_yaml = "\n".join(f"  - {t}" for t in top_tags) if top_tags else ""
        tags_block = f"tags:\n{tags_yaml}" if tags_yaml else "tags: []"

        content = (
            f"---\n"
            f"title: {title}\n"
            f"type: index\n"
            f"importance: 6\n"
            f"{tags_block}\n"
            f"---\n\n"
            f"{description}\n\n"
            f"## Members\n\n"
            f"{member_lines}\n"
        )

        slug = _slugify(title)
        target = vault.notes_dir / f"{slug}.md"
        counter = 2
        while target.exists():
            target = vault.notes_dir / f"{slug}-{counter}.md"
            counter += 1
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Created hub note '{title}' at {target} (run `pkm index` to update hub matching)"
    except Exception as e:
        return f"Error creating hub note: {str(e)}"
