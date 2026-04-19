"""AST parsing and graph generation for PKM."""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mistletoe
from mistletoe.ast_renderer import ASTRenderer
import networkx as nx

from pkm.config import VaultConfig
from pkm.frontmatter import parse as parse_note


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

        import re

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

        graph.add_node(
            note_id,
            type="note",
            title=note.title,
            path=str(file_path),
            meta=note.meta,
        )

        for tag in metadata.tags:
            tag_id = f"tag:{tag}"
            graph.add_node(tag_id, type="tag", name=tag)
            graph.add_edge(note_id, tag_id, type="has_tag")

        for link in metadata.links:
            graph.add_node(link, type="note_or_unresolved", title=link)
            graph.add_edge(note_id, link, type="wikilink")

    import datetime

    def _default(obj: object) -> str:
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return str(obj)
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    graph_data = nx.node_link_data(graph)
    graph_path.write_text(
        json.dumps(graph_data, ensure_ascii=False, indent=2, default=_default),
        encoding="utf-8",
    )
