"""Background daemon for fast semantic search and LLM task orchestration."""

import asyncio
import datetime
import fcntl
import importlib.metadata as meta
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from pathlib import Path as _Path
from typing import Dict, Any, Optional

import networkx as nx
import yaml

from pkm.config import discover_vaults, get_vault
from pkm.credential_store import agent_credential_env
from pkm.workflows import WorkflowConfig, load_workflows, jitter_minutes
from pkm.frontmatter import parse
from pkm.search_engine import is_index_stale, search, _require_transformers
from pkm.search_service import get_cached_index, resolve_search_vault, run_in_process_search

SOCKET_PATH = Path.home() / ".config" / "pkm" / "daemon.sock"
LOCK_PATH = Path.home() / ".config" / "pkm" / "daemon.lock"
LOG_PATH = Path.home() / ".config" / "pkm" / "daemon.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
IDLE_TIMEOUT = 3600
KEEPALIVE_ENV = "PKM_DAEMON_KEEPALIVE"
AUTO_INDEX_ENABLED_ENV = "PKM_DAEMON_AUTO_INDEX_ENABLED"
AUTO_INDEX_IDLE_ENV = "PKM_DAEMON_AUTO_INDEX_IDLE_SECONDS"
AUTO_INDEX_POLL_ENV = "PKM_DAEMON_AUTO_INDEX_POLL_SECONDS"
AUTO_INDEX_MIN_INTERVAL_ENV = "PKM_DAEMON_AUTO_INDEX_MIN_INTERVAL_SECONDS"
DEFAULT_AUTO_INDEX_IDLE_SECONDS = 300.0
DEFAULT_AUTO_INDEX_POLL_SECONDS = 60.0
DEFAULT_AUTO_INDEX_MIN_INTERVAL_SECONDS = 300.0

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("pkm.daemon")

_index_build_lock: asyncio.Lock | None = None
_index_schedule_lock: asyncio.Lock | None = None


def _activity_now() -> float:
    """Return monotonic time for idle accounting."""
    return time.monotonic()


def _web_listen_url(bind: str, port: int) -> str:
    """Return a readable local web URL for startup logs."""
    host = f"[{bind}]" if ":" in bind and not bind.startswith("[") else bind
    return f"http://{host}:{port}"


def _announce_web_server_started(bind: str, port: int) -> None:
    """Log web startup to both daemon log and systemd journal stdout."""
    message = f"PKM web server listening on {_web_listen_url(bind, port)}"
    logger.info(message)
    print(message, flush=True)


def _record_local_date(record: dict[str, Any]) -> datetime.date | None:
    value = record.get("time")
    if not isinstance(value, str):
        return None

    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.date()


def _workflow_marker_blocks_scheduled_run(
    *,
    vault_path: Path,
    workflow_id: str,
    marker_path: Path,
    current_date: datetime.date,
    hostname: str,
) -> tuple[bool, str | None]:
    if not marker_path.exists():
        return False, None

    try:
        data = json.loads(marker_path.read_text(encoding="utf-8"))
    except Exception:
        return False, None

    if data.get("date") != str(current_date):
        return False, None

    marker_host = str(data.get("host") or "unknown")
    if marker_host == hostname:
        return True, marker_host

    try:
        from pkm.workflows.history import read_workflow_history

        records = read_workflow_history(vault_path, workflow_id=workflow_id, limit=200)
    except Exception:
        return True, marker_host

    today_records = [
        record for record in records if _record_local_date(record) == current_date
    ]
    if any(
        record.get("status") == "success" and record.get("phase") == "complete"
        for record in today_records
    ):
        return True, marker_host

    marker_host_failed = any(
        record.get("hostname") == marker_host and record.get("status") == "failure"
        for record in today_records
    )
    return not marker_host_failed, marker_host


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
    last_activity = _activity_now()
    active_requests = 0
    graph_ready = False
    shutdown_gate = None  # ShutdownGate | None
    web_runner = None  # aiohttp.web.AppRunner | None
    current_task: Optional[Dict[str, Any]] = None
    auto_index_last_attempt: dict[str, float] = {}
    indexing_vaults: set[str] = set()


def _bump_activity() -> None:
    DaemonState.last_activity = _activity_now()


def _begin_request() -> None:
    DaemonState.active_requests = getattr(DaemonState, "active_requests", 0) + 1
    _bump_activity()


def _end_request() -> None:
    DaemonState.active_requests = max(
        0, getattr(DaemonState, "active_requests", 0) - 1
    )
    _bump_activity()


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    try:
        value = float(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value >= minimum else default


def _auto_index_enabled() -> bool:
    return _env_bool(AUTO_INDEX_ENABLED_ENV, True)


def _auto_index_idle_seconds() -> float:
    return _env_float(AUTO_INDEX_IDLE_ENV, DEFAULT_AUTO_INDEX_IDLE_SECONDS)


def _auto_index_poll_seconds() -> float:
    return _env_float(AUTO_INDEX_POLL_ENV, DEFAULT_AUTO_INDEX_POLL_SECONDS, minimum=1.0)


def _auto_index_min_interval_seconds() -> float:
    return _env_float(
        AUTO_INDEX_MIN_INTERVAL_ENV, DEFAULT_AUTO_INDEX_MIN_INTERVAL_SECONDS
    )


def _get_index_build_lock() -> asyncio.Lock:
    global _index_build_lock
    if _index_build_lock is None:
        _index_build_lock = asyncio.Lock()
    return _index_build_lock


def _get_index_schedule_lock() -> asyncio.Lock:
    global _index_schedule_lock
    if _index_schedule_lock is None:
        _index_schedule_lock = asyncio.Lock()
    return _index_schedule_lock


def _latest_indexable_source_mtime(vault) -> float:
    latest = 0.0
    for directory in (vault.notes_dir, vault.daily_dir, vault.tags_dir):
        if not directory.is_dir():
            continue
        for md_file in directory.glob("*.md"):
            try:
                latest = max(latest, md_file.stat().st_mtime)
            except OSError:
                continue
    return latest


def _run_index_update(vault, *, max_passes: int = 2) -> int:
    """Rebuild a vault index and refresh daemon caches."""
    from pkm.search_engine import build_index

    result = None
    for pass_index in range(max_passes):
        build_started_at = time.time()
        result = build_index(vault)
        get_cached_index.cache_clear()
        get_cached_graph.cache_clear()
        _reload_vault_caches(vault)
        if _latest_indexable_source_mtime(vault) <= build_started_at:
            break
        logger.info(
            "Vault '%s' changed during index build pass %d; retrying once.",
            vault.name,
            pass_index + 1,
        )
    return len(result.entries) if result is not None else 0


async def _update_index_for_vault(vault, *, reason: str) -> dict[str, Any]:
    vault_key = str(vault.path)
    async with _get_index_schedule_lock():
        indexing_vaults = getattr(DaemonState, "indexing_vaults", set())
        if vault_key in indexing_vaults:
            return {"status": "skipped", "reason": "already-indexing", "vault": vault.name}
        indexing_vaults.add(vault_key)
        DaemonState.indexing_vaults = indexing_vaults

    try:
        async with _get_index_build_lock():
            if reason.startswith("auto") and not is_index_stale(vault):
                return {"status": "skipped", "reason": "fresh", "vault": vault.name}
            loop = asyncio.get_running_loop()
            count = await loop.run_in_executor(None, _run_index_update, vault)
            logger.info(
                "Index updated for vault '%s' via %s (%d entries).",
                vault.name,
                reason,
                count,
            )
            return {
                "status": "indexed",
                "vault": vault.name,
                "reason": reason,
                "count": count,
            }
    except Exception as exc:
        logger.exception(
            "Failed to update index for vault '%s' via %s", vault.name, reason
        )
        return {
            "status": "error",
            "vault": vault.name,
            "reason": reason,
            "error": str(exc),
        }
    finally:
        async with _get_index_schedule_lock():
            getattr(DaemonState, "indexing_vaults", set()).discard(vault_key)


def _daemon_has_active_work() -> bool:
    return bool(
        getattr(DaemonState, "active_requests", 0) > 0
        or getattr(DaemonState, "current_task", None) is not None
        or getattr(DaemonState, "indexing_vaults", set())
    )


async def run_auto_index_once(now: float | None = None) -> list[dict[str, Any]]:
    """Run one idle auto-index pass for stale vaults, if daemon is idle."""
    if not _auto_index_enabled():
        return []
    current = _activity_now() if now is None else now
    if _daemon_has_active_work():
        return []
    if current - getattr(DaemonState, "last_activity", current) < _auto_index_idle_seconds():
        return []

    results: list[dict[str, Any]] = []
    min_interval = _auto_index_min_interval_seconds()
    last_attempts = getattr(DaemonState, "auto_index_last_attempt", {})
    for vault in discover_vaults().values():
        vault_key = str(vault.path)
        previous_attempt = last_attempts.get(vault_key)
        if previous_attempt is not None and current - previous_attempt < min_interval:
            continue
        try:
            if not is_index_stale(vault):
                continue
        except Exception:
            logger.exception("Failed to check stale index state for vault '%s'", vault.name)
            continue

        last_attempts[vault_key] = current
        DaemonState.auto_index_last_attempt = last_attempts
        results.append(await _update_index_for_vault(vault, reason="auto-idle"))
    return results


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
        worker_env = {**os.environ, "PKM_VAULT_DIR": vault_dir}
        worker_env.setdefault("PKM_WORKER_SANDBOX_PROFILE", "trusted-native")

        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(worker_script),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=worker_env,
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

        while True:
            line = await self.process.stdout.readline()
            if not line:
                break

            try:
                msg = _decode_worker_stdout_line(line)
                if msg is None:
                    continue
                if msg.get("type") == "stream":
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


def _decode_worker_stdout_line(line: bytes) -> dict[str, Any] | None:
    text = line.decode(errors="replace").strip()
    if not text:
        return None
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        logger.debug("Ignoring non-JSON worker stdout: %s", text[:240])
        return None
    if not isinstance(decoded, dict):
        logger.debug("Ignoring non-object worker stdout JSON: %s", text[:240])
        return None
    return decoded


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    _begin_request()
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

            vault = resolve_search_vault(vault_name)
            if not vault:
                writer.write(b"[]\n")
                return

            try:
                results, _stale_warning = await run_in_process_search(
                    query=query,
                    vault=vault,
                    top=top_n,
                    min_importance=min_importance,
                    memory_type=memory_type_filter,
                    recency_weight=recency_weight,
                )
            except FileNotFoundError:
                writer.write(b"[]\n")
                return

            response_obj = {
                "results": [asdict(r) for r in results],
                "graph_ready": DaemonState.graph_ready,
            }

            res_data = json.dumps(response_obj) + "\n"
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
                asyncio.create_task(_update_index_for_vault(vault, reason="manual"))
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

            task_id = f"sock_ask_{uuid.uuid4().hex}"
            task = {
                "type": "task",
                "id": task_id,
                "task_type": "ask",
                "query": query,
                "context": context_str,
                "model": req.get("model", "auto"),
                "model_candidates": req.get("model_candidates"),
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
        _end_request()


async def idle_checker(server: asyncio.Server):
    if _idle_timeout_disabled():
        logger.info("Idle timeout disabled by %s.", KEEPALIVE_ENV)
        return
    while True:
        await asyncio.sleep(60)
        if _activity_now() - DaemonState.last_activity > IDLE_TIMEOUT:
            logger.info("Idle timeout reached. Shutting down daemon.")
            server.close()
            break


async def auto_index_checker():
    while True:
        await asyncio.sleep(_auto_index_poll_seconds())
        try:
            results = await run_auto_index_once()
            for result in results:
                logger.info("Auto-index result: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Idle auto-index check failed")


def _idle_timeout_disabled() -> bool:
    return os.environ.get(KEEPALIVE_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def process_background_tasks():
    while True:
        if task_queue and worker_proxy:
            task = task_queue.peek()
            if task:
                try:
                    task = task_queue.pop()
                    if task:
                        logger.info(f"Processing background task: {task.get('id')}")
                        DaemonState.current_task = task
                        try:
                            await worker_proxy.send_task(task)
                        finally:
                            DaemonState.current_task = None
                except Exception:
                    logger.exception(
                        f"Error processing background task: {task.get('id') if task else 'unknown'}"
                    )

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
                # Drain web requests before exec
                gate = DaemonState.shutdown_gate
                if gate is not None:
                    gate.begin_drain()
                    try:
                        await asyncio.wait_for(gate.wait_idle(), 5.0)
                    except asyncio.TimeoutError:
                        logger.warning("Drain wait timed out — forcing restart")
                    gate.cancel_all()
                if DaemonState.web_runner is not None:
                    await DaemonState.web_runner.cleanup()
                server.close()
                SOCKET_PATH.unlink(missing_ok=True)
                os.execv(sys.executable, [sys.executable, "-m", "pkm.daemon"])
        except Exception as e:
            logger.warning("Version check error: %s", e)


async def workflow_checker(config: WorkflowConfig):
    """Schedule and dispatch a workflow based on its WorkflowConfig."""
    import socket

    last_run_dates: dict[str, datetime.date] = {}
    hostname = socket.gethostname()

    while True:
        await asyncio.sleep(60)

        now = datetime.datetime.now()
        current_date = now.date()

        if not task_queue:
            continue

        vaults = discover_vaults()
        ts = int(now.timestamp())
        for vault_name, vault in vaults.items():
            latest_configs = {wf.id: wf for wf in load_workflows(vault_path=vault.path)}
            latest_config = latest_configs.get(config.id)
            if latest_config is None:
                logger.info(
                    "Workflow '%s' no longer configured for vault '%s'; skipping",
                    config.id,
                    vault_name,
                )
                continue

            jitter_min = jitter_minutes(latest_config)
            if now.hour != latest_config.schedule_hour or now.minute != jitter_min:
                continue

            if last_run_dates.get(vault_name) == current_date:
                continue

            if not latest_config.enabled:
                logger.info(
                    "Workflow '%s' is disabled for vault '%s'; skipping scheduled run",
                    latest_config.id,
                    vault_name,
                )
                last_run_dates[vault_name] = current_date
                continue

            marker_path = vault.pkm_dir / latest_config.marker_file
            marker_blocks, marker_host = _workflow_marker_blocks_scheduled_run(
                vault_path=vault.path,
                workflow_id=latest_config.id,
                marker_path=marker_path,
                current_date=current_date,
                hostname=hostname,
            )
            if marker_blocks:
                logger.info(
                    "Workflow '%s' already claimed by '%s' today, skipping vault '%s'",
                    latest_config.id,
                    marker_host or "unknown",
                    vault_name,
                )
                last_run_dates[vault_name] = current_date
                continue
            if marker_host and marker_host != hostname:
                logger.info(
                    "Workflow '%s' claim by '%s' failed today; allowing '%s' to retry vault '%s'",
                    latest_config.id,
                    marker_host,
                    hostname,
                    vault_name,
                )

            vault.pkm_dir.mkdir(parents=True, exist_ok=True)
            marker_path.write_text(
                json.dumps({"date": str(current_date), "host": hostname})
            )

            task = {
                "type": "task",
                "id": f"{latest_config.id}_{vault_name}_{ts}",
                "task_type": "workflow",
                "workflow_id": latest_config.id,
                "model": latest_config.model,
                "workflow_source": "scheduled",
                "env_keys": agent_credential_env(),
                "env": {"PKM_VAULT_DIR": str(vault.path)},
            }
            task_queue.push(task)
            last_run_dates[vault_name] = current_date
            logger.info(
                "Scheduled workflow '%s' for vault '%s': %s (host=%s, slot=%d:%02d)",
                latest_config.id,
                vault_name,
                task["id"],
                hostname,
                latest_config.schedule_hour,
                jitter_min,
            )


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

    # Start aiohttp web server (requires [web] extra — skipped gracefully if absent)
    try:
        from pkm.config import get_web_config
        from pkm.web.server import make_app
        from pkm.web.shutdown import ShutdownGate
        import aiohttp.web as _aiohttp_web

        web_cfg = get_web_config()
        gate = ShutdownGate()
        DaemonState.shutdown_gate = gate
        web_app = make_app(
            gate=gate,
            web_config=web_cfg,
            on_activity=_bump_activity,
            search_runner=run_in_process_search,
        )
        runner = _aiohttp_web.AppRunner(web_app)
        await runner.setup()
        site = _aiohttp_web.TCPSite(runner, web_cfg.bind, web_cfg.port)
        await site.start()
        DaemonState.web_runner = runner
        _announce_web_server_started(web_cfg.bind, web_cfg.port)
    except ImportError:
        logger.info("aiohttp not installed — web server disabled (install [web] extra)")
    except Exception:
        logger.exception("Failed to start web server — continuing without it")

    checker_task = asyncio.create_task(idle_checker(server))
    auto_index_task = asyncio.create_task(auto_index_checker())
    workflows = load_workflows()
    workflow_tasks = [asyncio.create_task(workflow_checker(wf)) for wf in workflows]
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
        auto_index_task.cancel()
        for wt in workflow_tasks:
            wt.cancel()
        bg_task.cancel()
        version_task.cancel()
        if worker_proxy and worker_proxy.process:
            worker_proxy.process.terminate()
        if DaemonState.web_runner is not None:
            try:
                await DaemonState.web_runner.cleanup()
            except Exception:
                pass
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
