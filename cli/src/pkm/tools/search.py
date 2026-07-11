"""Vault-scoped graph discovery domain operations."""

from __future__ import annotations

import json
import re

from pkm.config import VaultConfig


def _slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.strip().lower())
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-") or "hub-note"


def find_surprising_connections(vault: VaultConfig, top_n: int = 20) -> str:
    """Format semantic bridge notes from the enriched graph."""
    from pkm.graph import find_surprising_connections as find_connections

    results = find_connections(vault, top_n=top_n)
    if not results:
        return "No surprising connections found (run `pkm index` first to build enriched graph)."
    return "\n".join(
        f"[[{item['title']}]] bridges cluster {item['cluster_a']}↔{item['cluster_b']}"
        f" (score={item['bridge_score']:.3f}, dist_a={item['dist_a']:.2f},"
        f" dist_b={item['dist_b']:.2f})"
        for item in results
    )


def list_clusters(vault: VaultConfig) -> str:
    """Return cluster membership, drift, and nearest index-note hubs as JSON."""
    enriched_path = vault.pkm_dir / "graph_enriched.json"
    if not enriched_path.exists():
        return "No enriched graph found (run `pkm index` first)."
    data = json.loads(enriched_path.read_text(encoding="utf-8"))
    clusters = data.get("clusters", [])
    if not clusters:
        return "No clusters found in enriched graph."

    import numpy as np

    from pkm.frontmatter import parse
    from pkm.graph import _cosine_distance, _load_embeddings_from_vector_db

    embeddings = _load_embeddings_from_vector_db(vault)
    index_notes = []
    if vault.notes_dir.is_dir():
        for path in sorted(vault.notes_dir.glob("*.md")):
            try:
                note = parse(path)
                note_id = str(note.id)
                if note.meta.get("type") == "index" and note_id in embeddings:
                    index_notes.append((note.title, embeddings[note_id]))
            except Exception:
                continue

    centroids = {
        cluster["id"]: np.array(cluster["centroid"], dtype="<f4")
        for cluster in clusters
        if cluster.get("id") is not None and cluster.get("centroid") is not None
    }
    items = []
    for cluster in clusters:
        cluster_id = cluster.get("id")
        hub_note = None
        if index_notes and cluster_id in centroids:
            distance, title = min(
                (
                    _cosine_distance(embedding, centroids[cluster_id]),
                    title,
                )
                for title, embedding in index_notes
            )
            if distance < 0.3:
                hub_note = title
        items.append(
            {
                "id": cluster_id,
                "member_count": len(cluster.get("members", [])),
                "top_tags": cluster.get("top_tags", []),
                "hub_note": hub_note,
                "centroid_drift": cluster.get("centroid_drift"),
                "is_new": bool(cluster.get("is_new")),
            }
        )
    return json.dumps({"clusters": items}, ensure_ascii=False, indent=2)


def list_god_nodes(vault: VaultConfig, top_n: int = 10) -> str:
    """Format the highest centrality note nodes in the best available graph."""
    import networkx as nx

    enriched_path = vault.pkm_dir / "graph_enriched.json"
    graph_path = vault.pkm_dir / "graph.json"
    if enriched_path.exists():
        data = json.loads(enriched_path.read_text(encoding="utf-8"))
    elif graph_path.exists():
        data = json.loads(graph_path.read_text(encoding="utf-8"))
    else:
        return "No graph found (run `pkm index` first)."

    graph = nx.node_link_graph(data)
    note_nodes = [
        node for node, attrs in graph.nodes(data=True) if attrs.get("type") == "note"
    ]
    if not note_nodes:
        return "No note nodes found in graph."
    note_graph = graph.subgraph(note_nodes).to_undirected()
    degree = nx.degree_centrality(note_graph)
    betweenness = nx.betweenness_centrality(note_graph)
    scores = sorted(
        (
            (node, degree.get(node, 0.0) + betweenness.get(node, 0.0))
            for node in note_nodes
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )[:top_n]
    lines = [f"{'note_id':<40} {'centrality':<12}", "-" * 54]
    lines.extend(
        f"{graph.nodes[node].get('title', node):<40} {score:.4f}"
        for node, score in scores
    )
    return "\n".join(lines)


def create_hub_note(
    vault: VaultConfig, cluster_index: int, title: str, description: str
) -> str:
    """Create an index note for a cluster in an enriched graph."""
    enriched_path = vault.pkm_dir / "graph_enriched.json"
    if not enriched_path.exists():
        return "No enriched graph found (run `pkm index` first)."
    data = json.loads(enriched_path.read_text(encoding="utf-8"))
    cluster = next(
        (item for item in data.get("clusters", []) if item.get("id") == cluster_index),
        None,
    )
    if cluster is None:
        return f"Cluster {cluster_index} not found. Run list_clusters() to see available clusters."

    members = "\n".join(f"- [[{member}]]" for member in sorted(cluster.get("members", [])))
    tags = cluster.get("top_tags", [])
    tags_block = "tags: []" if not tags else "tags:\n" + "\n".join(f"  - {tag}" for tag in tags)
    content = (
        f"---\ntitle: {title}\ntype: index\nimportance: 6\n{tags_block}\n---\n\n"
        f"{description}\n\n## Members\n\n{members}\n"
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
