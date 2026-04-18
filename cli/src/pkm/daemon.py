"""Background daemon for fast semantic search."""

import json
import os
import socket
import socketserver
import threading
import time
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from pkm.search_engine import VectorIndex, IndexEntry, search, _require_transformers

import logging

SOCKET_PATH = Path.home() / ".config" / "pkm" / "daemon.sock"
LOG_PATH = Path.home() / ".config" / "pkm" / "daemon.log"
IDLE_TIMEOUT = 3600

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("pkm.daemon")


class DaemonState:
    last_activity = time.time()
    graph_ready = False


@lru_cache(maxsize=2)
def get_cached_graph(graph_path: str, graph_mtime: float):
    for _ in range(3):
        try:
            import networkx as nx

            path = Path(graph_path)
            if not path.exists():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            return nx.node_link_graph(data)
        except json.JSONDecodeError:
            time.sleep(0.1)
        except Exception:
            logger.exception("Failed to load cached graph")
            return None
    logger.error("Failed to load cached graph after retries")
    return None


@lru_cache(maxsize=2)
def get_cached_index(index_path: str, index_mtime: float) -> VectorIndex:
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


class SearchRequestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        DaemonState.last_activity = time.time()
        try:
            data = self.rfile.readline().decode("utf-8").strip()
            if not data:
                return

            req = json.loads(data)
            action = req.get("action", "search")
            logger.info(f"Received action: {action}")

            if action == "search":
                query = req.get("query", "")
                vault_name = req.get("vault_name")
                top_n = req.get("top_n", 10)
                min_importance = req.get("min_importance", 1.0)
                memory_type_filter = req.get("memory_type_filter")
                recency_weight = req.get("recency_weight", 0.0)
                include_graph_context = req.get("include_graph_context", False)

                if not query:
                    self.wfile.write(b"[]\n")
                    return

                from pkm.config import discover_vaults

                vaults = discover_vaults()
                if vault_name and vault_name in vaults:
                    vault = vaults[vault_name]
                else:
                    vault = next(iter(vaults.values())) if vaults else None

                if not vault:
                    self.wfile.write(b"[]\n")
                    return

                index_path = vault.pkm_dir / "index.json"
                if not index_path.exists():
                    self.wfile.write(b"[]\n")
                    return
                index_mtime = index_path.stat().st_mtime

                _require_transformers("all-MiniLM-L6-v2")

                index = get_cached_index(str(index_path), index_mtime)

                results = search(
                    query=query,
                    index=index,
                    top_n=top_n,
                    min_importance=min_importance,
                    memory_type_filter=memory_type_filter,
                    recency_weight=recency_weight,
                )

                response_obj = {
                    "results": [asdict(r) for r in results],
                    "graph_ready": DaemonState.graph_ready,
                }

                if include_graph_context and DaemonState.graph_ready:
                    pass

                res_data = json.dumps(response_obj) + "\n"
                self.wfile.write(res_data.encode("utf-8"))

            elif action == "get_graph_context":
                note_id = req.get("note_id")
                depth = req.get("depth", 1)
                vault_name = req.get("vault_name")

                if not note_id:
                    self.wfile.write(b'{"error": "missing note_id"}\n')
                    return

                if not DaemonState.graph_ready:
                    self.wfile.write(b'{"error": "graph not ready"}\n')
                    return

                from pkm.config import discover_vaults

                vaults = discover_vaults()
                if vault_name and vault_name in vaults:
                    vault = vaults[vault_name]
                else:
                    vault = next(iter(vaults.values())) if vaults else None

                if not vault:
                    self.wfile.write(b'{"error": "vault not found"}\n')
                    return

                graph_path = vault.pkm_dir / "graph.json"
                if not graph_path.exists():
                    self.wfile.write(b'{"error": "graph not found"}\n')
                    return
                graph_mtime = graph_path.stat().st_mtime

                graph = get_cached_graph(str(graph_path), graph_mtime)
                if not graph or note_id not in graph:
                    self.wfile.write(b'{"error": "note not found in graph"}\n')
                    return

                import networkx as nx

                subgraph = nx.ego_graph(graph, note_id, radius=depth)
                context = nx.node_link_data(subgraph)

                res_data = json.dumps(context) + "\n"
                self.wfile.write(res_data.encode("utf-8"))

            elif action in ("update_index", "RELOAD_INDEX"):
                vault_name = req.get("vault_name")

                from pkm.config import discover_vaults

                vaults = discover_vaults()
                if vault_name and vault_name in vaults:
                    vault = vaults[vault_name]
                else:
                    vault = next(iter(vaults.values())) if vaults else None

                if not vault:
                    self.wfile.write(b'{"error": "vault not found"}\n')
                    return

                if action == "update_index":

                    def _bg_update(v):
                        from pkm.search_engine import build_index

                        try:
                            build_index(v)
                        except Exception:
                            logger.exception("Failed to build index in background")
                        finally:
                            get_cached_index.cache_clear()
                            get_cached_graph.cache_clear()
                            _reload_vault_caches(v)

                    threading.Thread(
                        target=_bg_update, args=(vault,), daemon=True
                    ).start()
                else:
                    get_cached_index.cache_clear()
                    get_cached_graph.cache_clear()

                    threading.Thread(
                        target=_reload_vault_caches, args=(vault,), daemon=True
                    ).start()

                self.wfile.write(b'{"status": "ok"}\n')

        except Exception:
            logger.exception("Error handling request")
            self.wfile.write(b'{"error": "internal"}\n')
        finally:
            DaemonState.last_activity = time.time()


class TimeoutUnixServer(socketserver.UnixStreamServer):
    def server_bind(self):
        address = str(self.server_address)
        if os.path.exists(address):
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.connect(address)
                raise RuntimeError("Another daemon is already running.")
            except ConnectionRefusedError:
                os.unlink(address)
        super().server_bind()


def idle_checker(server):
    while True:
        time.sleep(60)
        if time.time() - DaemonState.last_activity > IDLE_TIMEOUT:
            logger.info("Idle timeout reached. Shutting down daemon.")
            server.shutdown()
            break


def _on_shutdown() -> None:
    """Auto-consolidate eligible daily notes across all vaults on daemon exit."""
    try:
        from pkm.config import discover_vaults
        from pkm.commands.consolidate import (
            _list_candidate_dates,
            _parse_frontmatter,
            _set_frontmatter_field,
        )

        vaults = discover_vaults()
        for vault in vaults.values():
            candidates = _list_candidate_dates(vault)
            if not candidates:
                continue

            marked = 0
            for date_str in candidates:
                note_path = vault.daily_dir / f"{date_str}.md"
                if not note_path.exists():
                    continue
                try:
                    text = note_path.read_text(encoding="utf-8")
                    fm = _parse_frontmatter(text)
                    if fm.get("consolidated", False):
                        continue
                    new_text = _set_frontmatter_field(text, "consolidated", True)
                    note_path.write_text(new_text, encoding="utf-8")
                    marked += 1
                except Exception:
                    logger.exception("Failed to consolidate %s", note_path)

            if marked > 0:
                signal_path = vault.pkm_dir / "zettel-pending"
                vault.pkm_dir.mkdir(parents=True, exist_ok=True)
                signal_path.write_text(
                    json.dumps(
                        {
                            "marked": marked,
                            "timestamp": time.strftime(
                                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                            ),
                        }
                    ),
                    encoding="utf-8",
                )
                logger.info(
                    "Auto-consolidated %d dailies in vault '%s'. Zettel-pending signal written.",
                    marked,
                    vault.name,
                )
    except Exception:
        logger.exception("Error during shutdown auto-consolidation")


def _preload_model():
    """Pre-load the sentence-transformers model so first search is fast."""
    try:
        _require_transformers("all-MiniLM-L6-v2")
        logger.info("Model pre-loaded successfully.")
    except Exception:
        logger.exception("Failed to pre-load model")

    try:
        from pkm.config import discover_vaults

        vaults = discover_vaults()
        for vault in vaults.values():
            graph_path = vault.pkm_dir / ".context" / "graph.json"

            if graph_path.exists():
                get_cached_graph(str(graph_path), graph_path.stat().st_mtime)

        DaemonState.graph_ready = True
        logger.info("Graph pre-loaded successfully.")
    except Exception:
        logger.exception("Failed to pre-load graph")


def _reload_vault_caches(vault):
    DaemonState.graph_ready = False
    try:
        graph_path = vault.pkm_dir / ".context" / "graph.json"
        if graph_path.exists():
            get_cached_graph(str(graph_path), graph_path.stat().st_mtime)
        logger.info("Graph cache reloaded successfully for vault %s.", vault.name)
    except Exception:
        logger.exception("Failed to reload graph cache")
    finally:
        DaemonState.graph_ready = True


def main():
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        server = TimeoutUnixServer(str(SOCKET_PATH), SearchRequestHandler)
    except RuntimeError:
        logger.warning("Another daemon is already running. Exiting.")
        return

    checker = threading.Thread(target=idle_checker, args=(server,), daemon=True)
    checker.start()

    # Pre-load model in background thread so daemon is ready for first request
    threading.Thread(target=_preload_model, daemon=True).start()

    logger.info("Daemon started. Listening on %s", SOCKET_PATH)
    try:
        server.serve_forever()
    finally:
        logger.info("Daemon shutting down.")
        _on_shutdown()
        if SOCKET_PATH.exists():
            try:
                SOCKET_PATH.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    main()
