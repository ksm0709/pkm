import json
import networkx as nx
from functools import lru_cache

@lru_cache(maxsize=2)
def get_cached_graph(graph_path: str, graph_mtime: float) -> nx.Graph | None:
    try:
        with open(graph_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return nx.node_link_graph(data)
    except Exception:
        return None

@lru_cache(maxsize=2)
def get_cached_ast(ast_path: str, ast_mtime: float) -> dict | None:
    try:
        with open(ast_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
