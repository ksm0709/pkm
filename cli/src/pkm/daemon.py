"""Background daemon for fast semantic search, indexing, and the web UI."""

import asyncio

import fcntl
import importlib.metadata as meta
import json
import logging
import os
import sys
import time

from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from pathlib import Path as _Path
from typing import Any

import networkx as nx
from pkm.config import discover_vaults
from pkm.search_engine import is_index_stale, _require_transformers
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

        elif action == "update_index" or action == "RELOAD_INDEX":
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
                if DaemonState.web_runner is not None:
                    await DaemonState.web_runner.cleanup()
                server.close()
                SOCKET_PATH.unlink(missing_ok=True)
                os.execv(sys.executable, [sys.executable, "-m", "pkm.daemon"])
        except Exception as e:
            logger.warning("Version check error: %s", e)


async def async_main():
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
        version_task.cancel()
        if DaemonState.web_runner is not None:
            try:
                await DaemonState.web_runner.cleanup()
            except Exception:
                pass

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
