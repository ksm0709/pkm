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

SOCKET_PATH = Path.home() / ".config" / "pkm" / "daemon.sock"
IDLE_TIMEOUT = 3600


class DaemonState:
    last_activity = time.time()


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

            if action == "search":
                query = req.get("query", "")
                index_path = req.get("index_path")
                index_mtime = req.get("index_mtime", 0.0)
                top_n = req.get("top_n", 10)
                min_importance = req.get("min_importance", 1.0)

                if not query or not index_path:
                    self.wfile.write(b"[]\n")
                    return

                _require_transformers("all-MiniLM-L6-v2")

                index = get_cached_index(index_path, index_mtime)

                results = search(
                    query=query, index=index, top_n=top_n, min_importance=min_importance
                )

                res_data = json.dumps([asdict(r) for r in results]) + "\n"
                self.wfile.write(res_data.encode("utf-8"))
            elif action == "update_index":
                vault_path = req.get("vault_path")
                if not vault_path:
                    self.wfile.write(b'{"error": "missing vault_path"}\n')
                    return

                from pkm.config import VaultConfig
                from pkm.search_engine import build_index

                vault = VaultConfig(name=Path(vault_path).name, path=Path(vault_path))
                build_index(vault)

                get_cached_index.cache_clear()

                self.wfile.write(b'{"status": "ok"}\n')

        except Exception:
            self.wfile.write(b"[]\n")
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
            server.shutdown()
            break


def main():
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        server = TimeoutUnixServer(str(SOCKET_PATH), SearchRequestHandler)
    except RuntimeError:
        return

    checker = threading.Thread(target=idle_checker, args=(server,), daemon=True)
    checker.start()

    try:
        server.serve_forever()
    finally:
        if SOCKET_PATH.exists():
            try:
                SOCKET_PATH.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    main()
