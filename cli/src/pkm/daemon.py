"""Background daemon for fast semantic search and LLM task orchestration."""

import asyncio
import datetime
import fcntl
import hashlib
import importlib.metadata as meta
import json
import logging
import os
import socket
import sys
import time
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from pathlib import Path as _Path
from typing import Dict, Any, Optional, cast

import networkx as nx
import yaml

from pkm.config import discover_vaults, get_vault
from pkm.frontmatter import parse
from pkm.search_engine import VectorIndex, IndexEntry, search, _require_transformers

SOCKET_PATH = Path.home() / ".config" / "pkm" / "daemon.sock"
LOCK_PATH = Path.home() / ".config" / "pkm" / "daemon.lock"
LOG_PATH = Path.home() / ".config" / "pkm" / "daemon.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
IDLE_TIMEOUT = 3600

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("pkm.daemon")


def _resolve_graph_path(vault, tier: str = "enriched"):
    """Return best-available graph path. Preferred: enriched, fallback: structural.

    tier="enriched" -> try graph_enriched.json first, fall back to graph.json.
    tier="structural" -> graph.json only.
    """
    if tier == "enriched":
        p = vault.pkm_dir / "graph_enriched.json"
        if p.exists():
            return p
    return vault.pkm_dir / "graph.json"


def redact(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            k: (
                "<REDACTED>"
                if "key" in k.lower() or "token" in k.lower()
                else redact(v)
            )
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [redact(i) for i in data]
    return data


class DaemonState:
    last_activity = time.time()
    graph_ready = False


@lru_cache(maxsize=4)
def get_cached_graph(graph_path: str, graph_mtime: float) -> nx.DiGraph | None:
    for _ in range(3):
        try:
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


class BudgetExhausted(Exception):
    pass


@dataclass
class TokenBudget:
    max_tokens: int
    window_seconds: int
    used_tokens: int = 0
    window_start: float = time.time()

    def check_and_consume(self, tokens: int):
        now = time.time()
        if now - self.window_start > self.window_seconds:
            self.window_start = now
            self.used_tokens = 0

        if self.used_tokens + tokens > self.max_tokens:
            raise BudgetExhausted(
                f"Token budget exhausted. Used {self.used_tokens}/{self.max_tokens} in current window."
            )

        self.used_tokens += tokens


class TaskQueue:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.queue = []
        self._load()

    def _load(self):
        if self.db_path.exists():
            try:
                self.queue = json.loads(self.db_path.read_text())
            except Exception:
                self.queue = []

    def _save(self):
        self.db_path.write_text(json.dumps(self.queue))

    def push(self, task: Dict[str, Any]):
        self.queue.append(task)
        self._save()

    def pop(self) -> Optional[Dict[str, Any]]:
        if self.queue:
            task = self.queue.pop(0)
            self._save()
            return task
        return None

    def peek(self) -> Optional[Dict[str, Any]]:
        if self.queue:
            return self.queue[0]
        return None


class LLMWorkerProxy:
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.pending_tasks: Dict[str, asyncio.Future[Any]] = {}
        self.stream_callbacks: Dict[str, Any] = {}

    async def start(self, vault_dir: str):
        import sys

        worker_script = Path(__file__).parent / "worker.py"

        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(worker_script),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PKM_VAULT_DIR": vault_dir},
        )

        asyncio.create_task(self._log_stderr())
        asyncio.create_task(self._handle_worker_stdout())

    async def _log_stderr(self):
        if not self.process or not self.process.stderr:
            return
        while True:
            line = await self.process.stderr.readline()
            if not line:
                break
            text = line.decode().strip()
            if "key" in text.lower() or "token" in text.lower():
                text = "<REDACTED>"
            logger.info(f"[Worker STDERR] {text}")

    async def _handle_worker_stdout(self):
        if not self.process or not self.process.stdout:
            return

        try:
            import litellm
        except ImportError:
            logger.error("litellm not installed")
            return

        while True:
            line = await self.process.stdout.readline()
            if not line:
                break

            try:
                msg = json.loads(line.decode().strip())
                if msg.get("type") == "llm_request":
                    req_id = msg.get("id")
                    messages = msg.get("messages", [])
                    model = msg.get("model", "gpt-4o-mini")

                    try:
                        self.budget.check_and_consume(0)

                        loop = asyncio.get_running_loop()
                        response = await loop.run_in_executor(
                            None,
                            lambda: litellm.completion(model=model, messages=messages),
                        )

                        response_any = cast(Any, response)
                        content = response_any.choices[0].message.content
                        usage = getattr(response_any, "usage", None)

                        if usage:
                            self.budget.check_and_consume(usage.total_tokens)

                        resp_msg = {
                            "type": "llm_response",
                            "id": req_id,
                            "content": content,
                        }
                        if self.process and self.process.stdin:
                            self.process.stdin.write(
                                (json.dumps(resp_msg) + "\n").encode()
                            )
                            await self.process.stdin.drain()

                    except BudgetExhausted as e:
                        err_msg = {"type": "llm_error", "id": req_id, "message": str(e)}
                        if self.process and self.process.stdin:
                            self.process.stdin.write(
                                (json.dumps(err_msg) + "\n").encode()
                            )
                            await self.process.stdin.drain()
                    except Exception as e:
                        logger.exception("LiteLLM call failed")
                        err_msg = {"type": "llm_error", "id": req_id, "message": str(e)}
                        if self.process and self.process.stdin:
                            self.process.stdin.write(
                                (json.dumps(err_msg) + "\n").encode()
                            )
                            await self.process.stdin.drain()

                elif msg.get("type") == "token_usage":
                    tokens = msg.get("tokens", 0)
                    try:
                        self.budget.check_and_consume(tokens)
                    except BudgetExhausted as e:
                        logger.warning(f"Budget exhausted: {e}")
                        if self.process and self.process.stdin:
                            abort_msg = {"type": "abort"}
                            self.process.stdin.write(
                                (json.dumps(abort_msg) + "\n").encode()
                            )
                            await self.process.stdin.drain()

                elif msg.get("type") == "stream":
                    task_id = msg.get("id")
                    if task_id in self.stream_callbacks:
                        try:
                            await self.stream_callbacks[task_id](msg)
                        except Exception:
                            pass
                elif msg.get("type") in ("result", "error"):
                    task_id = msg.get("id")
                    if task_id in self.pending_tasks:
                        future = self.pending_tasks.pop(task_id)
                        if not future.done():
                            future.set_result(msg)
                    if task_id in self.stream_callbacks:
                        self.stream_callbacks.pop(task_id, None)
            except Exception:
                logger.exception("Error handling worker message")

    async def send_task(
        self, task: Dict[str, Any], stream_callback=None
    ) -> Dict[str, Any]:
        if not self.process or not self.process.stdin:
            raise RuntimeError("Worker not running")

        task_id = str(task.get("id", ""))
        future = asyncio.Future()
        self.pending_tasks[task_id] = future

        if stream_callback:
            self.stream_callbacks[task_id] = stream_callback

        self.process.stdin.write((json.dumps(task) + "\n").encode())
        await self.process.stdin.drain()

        return await future


worker_proxy: Optional[LLMWorkerProxy] = None
task_queue: Optional[TaskQueue] = None


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    DaemonState.last_activity = time.time()
    try:
        data = await reader.readline()
        if not data:
            return

        req = json.loads(data.decode("utf-8").strip())
        action = req.get("action", "search")
        logger.info(f"Received action: {action}")

        if action == "search":
            query = req.get("query", "")
            vault_name = req.get("vault_name")
            top_n = req.get("top_n", 10)
            min_importance = req.get("min_importance", 1.0)
            memory_type_filter = req.get("memory_type_filter")
            recency_weight = req.get("recency_weight", 0.0)

            if not query:
                writer.write(b"[]\n")
                return

            vaults = discover_vaults()
            if vault_name and vault_name in vaults:
                vault = vaults[vault_name]
            else:
                vault = next(iter(vaults.values())) if vaults else None

            if not vault:
                writer.write(b"[]\n")
                return

            index_path = vault.pkm_dir / "index.json"
            if not index_path.exists():
                writer.write(b"[]\n")
                return
            index_mtime = index_path.stat().st_mtime

            _require_transformers("all-MiniLM-L6-v2")

            index = get_cached_index(str(index_path), index_mtime)

            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                None,
                lambda: search(
                    query=query,
                    index=index,
                    top_n=top_n,
                    min_importance=min_importance,
                    memory_type_filter=memory_type_filter,
                    recency_weight=recency_weight,
                ),
            )

            response_obj = {
                "results": [asdict(r) for r in results],
                "graph_ready": DaemonState.graph_ready,
            }

            res_data = json.dumps(response_obj) + "\n"
            writer.write(res_data.encode("utf-8"))

        elif action == "get_graph_context":
            note_id = req.get("note_id")
            depth = req.get("depth", 1)
            vault_name = req.get("vault_name")

            if not note_id:
                writer.write(b'{"error": "missing note_id"}\n')
                return

            if not DaemonState.graph_ready:
                writer.write(b'{"error": "graph not ready"}\n')
                return

            vaults = discover_vaults()
            if vault_name and vault_name in vaults:
                vault = vaults[vault_name]
            else:
                vault = next(iter(vaults.values())) if vaults else None

            if not vault:
                writer.write(b'{"error": "vault not found"}\n')
                return

            tier = req.get("tier", "enriched")
            graph_path = _resolve_graph_path(vault, tier)
            if not graph_path.exists():
                writer.write(b'{"error": "graph not found"}\n')
                return
            graph_mtime = graph_path.stat().st_mtime

            graph = get_cached_graph(str(graph_path), graph_mtime)
            if not graph or note_id not in graph:
                writer.write(b'{"error": "note not found in graph"}\n')
                return

            subgraph = nx.ego_graph(graph, note_id, radius=depth)
            context = nx.node_link_data(subgraph)

            res_data = json.dumps(context) + "\n"
            writer.write(res_data.encode("utf-8"))

        elif action in ("update_index", "RELOAD_INDEX"):
            vault_name = req.get("vault_name")

            vaults = discover_vaults()
            if vault_name and vault_name in vaults:
                vault = vaults[vault_name]
            else:
                vault = next(iter(vaults.values())) if vaults else None

            if not vault:
                writer.write(b'{"error": "vault not found"}\n')
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

                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, _bg_update, vault)
            else:
                get_cached_index.cache_clear()
                get_cached_graph.cache_clear()

                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, _reload_vault_caches, vault)

            writer.write(b'{"status": "ok"}\n')

        elif action == "ask":
            if not worker_proxy:
                writer.write(b'{"error": "LLM worker not initialized"}\n')
                return

            env_keys = req.get("env_keys", {})
            if env_keys:
                os.environ.update(env_keys)

            query = req.get("query")
            vault_name = req.get("vault_name")
            env_vars = req.get("env", {})
            for k, v in env_vars.items():
                os.environ[k] = v

            vaults = discover_vaults()
            if vault_name and vault_name in vaults:
                vault = vaults[vault_name]
            else:
                vault = next(iter(vaults.values())) if vaults else None

            context_str = ""
            if vault and query:
                index_path = vault.pkm_dir / "index.json"
                if index_path.exists():
                    index_mtime = index_path.stat().st_mtime
                    _require_transformers("all-MiniLM-L6-v2")
                    index = get_cached_index(str(index_path), index_mtime)

                    loop = asyncio.get_running_loop()
                    results = await loop.run_in_executor(
                        None,
                        lambda: search(
                            query=query,
                            index=index,
                            top_n=5,
                        ),
                    )

                    graph_depth = req.get("graph_depth", 0)

                    unique_note_ids = set()
                    notes_to_include = []

                    for res in results:
                        if res.note_id not in unique_note_ids:
                            unique_note_ids.add(res.note_id)
                            notes_to_include.append(
                                {"title": res.title, "path": res.path}
                            )

                    if graph_depth > 0 and DaemonState.graph_ready:
                        graph_path = _resolve_graph_path(vault, "enriched")
                        if graph_path.exists():
                            graph_mtime = graph_path.stat().st_mtime
                            graph = get_cached_graph(str(graph_path), graph_mtime)

                            if graph:
                                for res in results:
                                    if res.note_id in graph:
                                        subgraph = nx.ego_graph(
                                            graph, res.note_id, radius=graph_depth
                                        )
                                        for node_id, node_data in subgraph.nodes(
                                            data=True
                                        ):
                                            if (
                                                node_data.get("type") == "note"
                                                and node_id not in unique_note_ids
                                            ):
                                                unique_note_ids.add(node_id)
                                                notes_to_include.append(
                                                    {
                                                        "title": node_data.get(
                                                            "title", node_id
                                                        ),
                                                        "path": node_data.get("path"),
                                                    }
                                                )

                    context_parts = []
                    for note_info in notes_to_include:
                        try:
                            if note_info.get("path"):
                                note = parse(Path(note_info["path"]))
                                if note.meta:
                                    meta_str = yaml.dump(
                                        note.meta,
                                        allow_unicode=True,
                                        default_flow_style=False,
                                        sort_keys=False,
                                    ).strip()
                                    meta_section = f"Metadata:\n{meta_str}\n"
                                else:
                                    meta_section = "Metadata: None\n"

                                context_parts.append(
                                    f"--- Note: {note.title} ---\n{meta_section}\nContent:\n{note.body}\n"
                                )
                        except Exception as e:
                            logger.warning(f"Failed to read note for context: {e}")

                    context_str = "\n".join(context_parts)

            task_id = f"ask_{time.time()}"
            task = {
                "type": "task",
                "id": task_id,
                "task_type": "ask",
                "query": query,
                "context": context_str,
                "model": req.get("model", "gemini/gemini-3.1-flash-preview"),
                "reasoning_effort": req.get("reasoning_effort"),
                "env_keys": env_keys,
                "env": {"PKM_VAULT_DIR": str(vault.path)} if vault else {},
                "cwd": req.get("cwd"),
            }

            async def on_stream(msg):
                try:
                    writer.write((json.dumps(msg) + "\n").encode())
                    await writer.drain()
                except Exception:
                    pass

            try:
                result = await worker_proxy.send_task(task, stream_callback=on_stream)
                writer.write((json.dumps(result) + "\n").encode())
            except Exception as e:
                writer.write((json.dumps({"error": str(e)}) + "\n").encode())

        elif action == "queue_task":
            if not task_queue:
                writer.write(b'{"error": "Task queue not initialized"}\n')
                return

            task = req.get("task")
            if task:
                task_queue.push(task)
                writer.write(b'{"status": "queued"}\n')
            else:
                writer.write(b'{"error": "missing task"}\n')

    except Exception:
        logger.exception("Error handling request")
        writer.write(b'{"error": "internal"}\n')
    finally:
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        DaemonState.last_activity = time.time()


async def idle_checker(server: asyncio.Server):
    while True:
        await asyncio.sleep(60)
        if time.time() - DaemonState.last_activity > IDLE_TIMEOUT:
            logger.info("Idle timeout reached. Shutting down daemon.")
            server.close()
            break


async def process_background_tasks():
    while True:
        if task_queue and worker_proxy:
            task = task_queue.peek()
            if task:
                try:
                    worker_proxy.budget.check_and_consume(0)

                    task = task_queue.pop()
                    if task:
                        logger.info(f"Processing background task: {task.get('id')}")
                        await worker_proxy.send_task(task)
                except BudgetExhausted:
                    logger.info("Budget exhausted, pausing background tasks")
                    await asyncio.sleep(60)
                    continue
                except Exception:
                    logger.exception("Error processing background task")

        await asyncio.sleep(5)


def _on_shutdown() -> None:
    """Auto-consolidate eligible daily notes across all vaults on daemon exit."""
    try:
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
        vaults = discover_vaults()
        for vault in vaults.values():
            graph_path = _resolve_graph_path(vault, "enriched")
            if graph_path.exists():
                get_cached_graph(str(graph_path), graph_path.stat().st_mtime)

        DaemonState.graph_ready = True
        logger.info("Graph pre-loaded successfully.")
    except Exception:
        logger.exception("Failed to pre-load graph")


def _reload_vault_caches(vault):
    DaemonState.graph_ready = False
    try:
        graph_path = _resolve_graph_path(vault, "enriched")
        if graph_path.exists():
            get_cached_graph(str(graph_path), graph_path.stat().st_mtime)
        logger.info("Graph cache reloaded successfully for vault %s.", vault.name)
    except Exception:
        logger.exception("Failed to reload graph cache")
    finally:
        DaemonState.graph_ready = True


async def version_checker(server: asyncio.Server):
    try:
        dist = meta.distribution("pkm")
        metadata_file = _Path(str(dist.locate_file("METADATA")))
        startup_mtime = metadata_file.stat().st_mtime
        startup_version = dist.version
    except Exception:
        return

    while True:
        await asyncio.sleep(60)
        try:
            current_mtime = metadata_file.stat().st_mtime
            if current_mtime != startup_mtime:
                current_version = meta.Distribution.from_name("pkm").version
                logger.info(
                    "PKM updated %s → %s, restarting daemon.",
                    startup_version,
                    current_version,
                )
                server.close()
                SOCKET_PATH.unlink(missing_ok=True)
                os.execv(sys.executable, [sys.executable, "-m", "pkm.daemon"])
        except Exception as e:
            logger.warning("Version check error: %s", e)


async def maintenance_checker():
    last_run_date = None
    hostname = socket.gethostname()
    # Deterministic 0-29 min offset per host so machines don't pile up at 2:00 AM.
    # Same host always gets the same slot; no shared state needed.
    jitter_min = int(hashlib.md5(hostname.encode()).hexdigest(), 16) % 30

    while True:
        await asyncio.sleep(60)

        now = datetime.datetime.now()
        current_date = now.date()

        if now.hour == 2 and now.minute == jitter_min and last_run_date != current_date:
            if task_queue:
                vaults = discover_vaults()
                ts = int(now.timestamp())
                for vault_name, vault in vaults.items():
                    # Belt-and-suspenders: check vault-level marker written by whichever
                    # machine ran first today (marker lives inside the synced vault).
                    marker_path = vault.pkm_dir / "zettel-last-run"
                    if marker_path.exists():
                        try:
                            data = json.loads(marker_path.read_text())
                            if data.get("date") == str(current_date):
                                logger.info(
                                    "Zettelkasten maintenance already claimed by '%s' today, skipping vault '%s'",
                                    data.get("host", "unknown"),
                                    vault_name,
                                )
                                continue
                        except Exception:
                            pass

                    # Claim the slot before pushing the task so other machines that
                    # sync within the next few minutes will see today's marker and skip.
                    vault.pkm_dir.mkdir(parents=True, exist_ok=True)
                    marker_path.write_text(
                        json.dumps({"date": str(current_date), "host": hostname})
                    )

                    task = {
                        "type": "task",
                        "id": f"maint_{vault_name}_{ts}",
                        "task_type": "zettelkasten_maintenance",
                        "env": {"PKM_VAULT_DIR": str(vault.path)},
                    }
                    task_queue.push(task)
                    logger.info(
                        "Scheduled Zettelkasten maintenance for vault '%s': %s (host=%s, slot=2:%02d)",
                        vault_name,
                        task["id"],
                        hostname,
                        jitter_min,
                    )
            last_run_date = current_date


async def task_summary_checker():
    last_run_date = None
    hostname = socket.gethostname()
    # 0-29 min jitter per host so machines don't pile up at 08:00
    jitter_min = int(hashlib.md5((hostname + "summary").encode()).hexdigest(), 16) % 30

    while True:
        await asyncio.sleep(60)

        now = datetime.datetime.now()
        current_date = now.date()

        if now.hour == 8 and now.minute == jitter_min and last_run_date != current_date:
            if task_queue:
                vaults = discover_vaults()
                ts = int(now.timestamp())
                for vault_name, vault in vaults.items():
                    marker_path = vault.pkm_dir / "summary-last-run"
                    if marker_path.exists():
                        try:
                            data = json.loads(marker_path.read_text())
                            if data.get("date") == str(current_date):
                                logger.info(
                                    "Task summary already claimed by '%s' today, skipping vault '%s'",
                                    data.get("host", "unknown"),
                                    vault_name,
                                )
                                continue
                        except Exception:
                            pass

                    vault.pkm_dir.mkdir(parents=True, exist_ok=True)
                    marker_path.write_text(
                        json.dumps({"date": str(current_date), "host": hostname})
                    )

                    task = {
                        "type": "task",
                        "id": f"summary_{vault_name}_{ts}",
                        "task_type": "daily_task_summary",
                        "env": {"PKM_VAULT_DIR": str(vault.path)},
                    }
                    task_queue.push(task)
                    logger.info(
                        "Scheduled daily task summary for vault '%s': %s (host=%s, slot=8:%02d)",
                        vault_name,
                        task["id"],
                        hostname,
                        jitter_min,
                    )
            last_run_date = current_date


async def async_main():
    global worker_proxy, task_queue

    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(SOCKET_PATH.parent, 0o700)

    # Acquire exclusive flock — OS auto-releases on process death (even SIGKILL)
    _lock_fd = open(LOCK_PATH, "w")
    try:
        fcntl.flock(_lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        logger.warning("Another daemon is already running (lock held). Exiting.")
        _lock_fd.close()
        return
    _lock_fd.write(str(os.getpid()))
    _lock_fd.flush()

    # Clean up stale socket from a crashed daemon
    SOCKET_PATH.unlink(missing_ok=True)

    queue_path = Path.home() / ".config" / "pkm" / "task_queue.json"
    task_queue = TaskQueue(queue_path)

    worker_proxy = LLMWorkerProxy()

    try:
        active_vault = get_vault()
        vault_dir = str(active_vault.path)
    except Exception:
        vaults = discover_vaults()
        vault_dir = str(next(iter(vaults.values())).path) if vaults else "."

    await worker_proxy.start(vault_dir)

    server = await asyncio.start_unix_server(handle_client, str(SOCKET_PATH))
    os.chmod(str(SOCKET_PATH), 0o600)

    checker_task = asyncio.create_task(idle_checker(server))
    maint_task = asyncio.create_task(maintenance_checker())
    summary_task = asyncio.create_task(task_summary_checker())
    bg_task = asyncio.create_task(process_background_tasks())
    version_task = asyncio.create_task(version_checker(server))

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _preload_model)

    logger.info("Daemon started. Listening on %s", SOCKET_PATH)
    try:
        async with server:
            await server.serve_forever()
    finally:
        logger.info("Daemon shutting down.")
        checker_task.cancel()
        maint_task.cancel()
        summary_task.cancel()
        bg_task.cancel()
        version_task.cancel()
        if worker_proxy and worker_proxy.process:
            worker_proxy.process.terminate()
        _on_shutdown()
        if SOCKET_PATH.exists():
            try:
                SOCKET_PATH.unlink()
            except OSError:
                pass
        try:
            _lock_fd.close()
            LOCK_PATH.unlink(missing_ok=True)
        except Exception:
            pass


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
