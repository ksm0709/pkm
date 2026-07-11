"""Vault-scoped graph and wikilink domain operations."""

from __future__ import annotations

import json
import re
from typing import Any

import networkx as nx

from pkm.config import VaultConfig


def add_wikilink(
    vault: VaultConfig,
    source_note_id: str,
    target_note_id: str,
    description: str,
) -> str:
    """Append a described wikilink to a source note's Related section."""
    source_path = next(
        (
            directory / f"{source_note_id}.md"
            for directory in (vault.notes_dir, vault.daily_dir)
            if (directory / f"{source_note_id}.md").exists()
        ),
        None,
    )
    if source_path is None:
        return f"Error: source note '{source_note_id}' not found."

    text = source_path.read_text(encoding="utf-8")
    link_entry = f"- [[{target_note_id}|{description}]]"
    match = re.search(r"^## Related\s*$", text, re.MULTILINE)
    if match:
        rest = text[match.end() :]
        insert_at = match.end() + len(rest) - len(rest.lstrip("\n"))
        text = text[:insert_at] + link_entry + "\n" + text[insert_at:]
    else:
        if not text.endswith("\n"):
            text += "\n"
        text += f"\n## Related\n\n{link_entry}\n"

    source_path.write_text(text, encoding="utf-8")
    return f"Added [[{target_note_id}]] to {source_path}"


def _get_note_neighbors_data(
    vault: VaultConfig, note_id: str, include_semantic: bool = False
) -> dict[str, Any]:
    """Return structural and optional semantic neighbors for a vault note."""
    graph_path = vault.pkm_dir / "graph.json"
    if not graph_path.exists():
        raise FileNotFoundError("graph not found — run pkm index first")

    graph = nx.node_link_graph(json.loads(graph_path.read_text(encoding="utf-8")))
    if note_id not in graph:
        return {"note_id": note_id, "outbound": [], "inbound": [], "semantic": []}

    def node_data(node_id: str) -> dict[str, Any]:
        return {
            "note_id": node_id,
            "title": graph.nodes[node_id].get("title", node_id),
            "type": graph.nodes[node_id].get("type", "note"),
        }

    outbound = [node_data(node_id) for node_id in graph.successors(note_id)]
    inbound = [node_data(node_id) for node_id in graph.predecessors(note_id)]
    semantic: list[dict[str, Any]] = []
    if include_semantic:
        enriched_path = vault.pkm_dir / "graph_enriched.json"
        if enriched_path.exists():
            enriched = nx.node_link_graph(
                json.loads(enriched_path.read_text(encoding="utf-8"))
            )
            seen: set[str] = set()
            for source, target, edge in enriched.edges(data=True):
                if edge.get("type") != "semantic_similar":
                    continue
                neighbor = (
                    target
                    if source == note_id
                    else source if target == note_id else None
                )
                if neighbor is None or neighbor in seen:
                    continue
                seen.add(neighbor)
                semantic.append(
                    {
                        "note_id": neighbor,
                        "title": enriched.nodes[neighbor].get("title", neighbor),
                        "type": enriched.nodes[neighbor].get("type", "note"),
                        "confidence": edge.get("confidence", 0.0),
                    }
                )

    return {
        "note_id": note_id,
        "outbound": outbound,
        "inbound": inbound,
        "semantic": semantic,
    }
