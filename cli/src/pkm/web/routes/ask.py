"""SSE ask route — POST /api/v1/vault/{name}/ask.

Streams chunks from ``LLMWorkerProxy.send_task`` to the client as
Server-Sent Events.  Each worker stream chunk becomes one SSE event whose
``event:`` line is the chunk's ``type`` field (``content``, ``tool_detail``,
``reasoning``, ``error``, ...) and whose ``data:`` is the chunk JSON.
The stream terminates with one of:

  * ``event: result\\ndata: {...}\\n\\n``   — worker finished successfully
  * ``event: error\\ndata: {...}\\n\\n``    — worker error or drain abort

While the stream is open a keepalive task bumps ``DaemonState.last_activity``
every 30 s so the idle_checker never fires mid-ask.  A drain hook registers
an ``asyncio.Event`` with ``DaemonState.shutdown_gate`` so daemon restarts
can short-circuit the stream within the 5 s drain window.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from aiohttp.client_exceptions import ClientConnectionResetError
from aiohttp import web

from pkm.config import load_config
from pkm.web.keepalive import run_keepalive
from pkm.web.routes.notes import _resolve_vault

logger = logging.getLogger("pkm.web.ask")

# Test-monkeypatchable keepalive cadence (seconds).  Production: 30 s.
KEEPALIVE_INTERVAL: float = 30.0
ASK_RUN_TTL_SECONDS: float = 30 * 60
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")


@dataclass
class AskRun:
    """In-memory record for one web ask execution.

    The worker execution is intentionally detached from the browser SSE
    connection.  Mobile browsers routinely suspend fetch streams when a tab or
    installed app is backgrounded; the run record lets the UI recover the final
    result without starting a duplicate agent turn.
    """

    run_id: str
    task_id: str
    created_at: float
    updated_at: float
    status: str = "running"
    revision: int = 0
    chunks: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    task: asyncio.Task | None = None
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)

    async def append_chunk(self, event: str, data: dict[str, Any]) -> None:
        async with self.condition:
            self.chunks.append(
                {"seq": len(self.chunks), "event": event, "data": data}
            )
            self.revision += 1
            self.updated_at = time.time()
            self.condition.notify_all()

    async def finish(self, payload: dict[str, Any]) -> None:
        async with self.condition:
            self.status = "done"
            self.result = payload
            self.revision += 1
            self.updated_at = time.time()
            self.condition.notify_all()

    async def fail(self, payload: dict[str, Any]) -> None:
        async with self.condition:
            self.status = "error"
            self.error = payload
            self.revision += 1
            self.updated_at = time.time()
            self.condition.notify_all()

    async def wait_for_revision(self, revision: int) -> None:
        async with self.condition:
            await self.condition.wait_for(lambda: self.revision != revision)

    def snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "status": self.status,
            "revision": self.revision,
            "chunks": list(self.chunks),
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AskRunStore:
    def __init__(self) -> None:
        self.runs: dict[str, AskRun] = {}

    def cleanup(self) -> None:
        cutoff = time.time() - ASK_RUN_TTL_SECONDS
        expired = [
            run_id
            for run_id, run in self.runs.items()
            if run.status in {"done", "error"} and run.updated_at < cutoff
        ]
        for run_id in expired:
            self.runs.pop(run_id, None)

    def get(self, run_id: str) -> AskRun | None:
        self.cleanup()
        return self.runs.get(run_id)

    def get_or_create(self, run_id: str, task_id: str) -> tuple[AskRun, bool]:
        self.cleanup()
        existing = self.runs.get(run_id)
        if existing is not None:
            return existing, False
        now = time.time()
        run = AskRun(
            run_id=run_id,
            task_id=task_id,
            created_at=now,
            updated_at=now,
        )
        self.runs[run_id] = run
        return run, True


_ASK_RUN_STORE = AskRunStore()


def _sse_event(event: str, data: Any) -> bytes:
    """Encode one SSE event line block."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")


def _sse_comment(text: str) -> bytes:
    return f": {text}\n\n".encode("utf-8")


def _is_client_disconnect(exc: BaseException) -> bool:
    return isinstance(exc, (ConnectionResetError, ClientConnectionResetError))


async def _safe_write_sse(response: Any, event: str, data: Any) -> bool:
    try:
        await response.write(_sse_event(event, data))
        return True
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if _is_client_disconnect(exc):
            return False
        logger.exception("Failed to write SSE event")
        return False


async def _safe_write_sse_comment(response: Any, text: str) -> bool:
    try:
        await response.write(_sse_comment(text))
        return True
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if _is_client_disconnect(exc):
            return False
        logger.exception("Failed to write SSE heartbeat")
        return False


def _runtime_daemon_module() -> Any:
    """Return the live daemon module, including ``python -m pkm.daemon`` runs.

    When the daemon is launched with ``python -m pkm.daemon``, runtime globals
    such as ``worker_proxy`` live on ``__main__``.  Importing ``pkm.daemon`` from
    a route handler would create/read a second module instance with
    ``worker_proxy = None``, which turns healthy ask requests into 503s.
    """
    main_mod = sys.modules.get("__main__")
    main_spec = getattr(main_mod, "__spec__", None)
    if (
        getattr(main_spec, "name", None) == "pkm.daemon"
        and hasattr(main_mod, "worker_proxy")
        and hasattr(main_mod, "DaemonState")
    ):
        return main_mod

    from pkm import daemon as _daemon

    return _daemon


def _default_ask_options() -> tuple[str, str | None]:
    defaults = load_config().get("defaults", {})
    return defaults.get("model") or "auto", defaults.get("reasoning-effort")


def _ask_run_id(value: Any) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        if _RUN_ID_RE.fullmatch(candidate):
            return candidate
    return f"web-run-{uuid.uuid4().hex}"


async def get_ask_options(request: web.Request) -> web.Response:
    """GET /api/v1/vault/{name}/ask/options — expose resolved ask defaults."""
    _resolve_vault(request.match_info["name"])
    model, reasoning_effort = _default_ask_options()
    return web.json_response({"model": model, "reasoning_effort": reasoning_effort})


async def get_ask_run(request: web.Request) -> web.Response:
    """GET /api/v1/vault/{name}/ask/runs/{run_id} — recover ask run state."""
    _resolve_vault(request.match_info["name"])
    run_id = request.match_info["run_id"]
    run = _ASK_RUN_STORE.get(run_id)
    if run is None:
        raise web.HTTPNotFound(reason="Ask run not found")
    return web.json_response(run.snapshot())


async def _execute_ask_run(
    run: AskRun,
    worker_proxy: Any,
    task: dict[str, Any],
) -> None:
    async def on_stream(msg: dict) -> None:
        chunk = msg.get("chunk") or {}
        event_name = chunk.get("type") or "stream"
        await run.append_chunk(event_name, chunk)

    try:
        result = await worker_proxy.send_task(task, stream_callback=on_stream)
        if isinstance(result, dict) and result.get("type") == "error":
            await run.fail({"message": result.get("message", "")})
        else:
            payload = result.get("data", {}) if isinstance(result, dict) else {}
            await run.finish(payload)
    except asyncio.CancelledError:
        await run.fail({"reason": "cancelled"})
        raise
    except Exception as exc:
        logger.exception("Error in background ask run")
        await run.fail({"message": str(exc)})


async def _stream_ask_run(
    response: web.StreamResponse,
    run: AskRun,
    cancel_event: asyncio.Event,
) -> None:
    next_seq = 0
    while True:
        while next_seq < len(run.chunks):
            chunk = run.chunks[next_seq]
            if not await _safe_write_sse(response, chunk["event"], chunk["data"]):
                return
            next_seq += 1

        if run.status == "done":
            await _safe_write_sse(response, "result", run.result or {})
            return
        if run.status == "error":
            await _safe_write_sse(response, "error", run.error or {"message": "error"})
            return

        observed_revision = run.revision
        change_wait = asyncio.create_task(run.wait_for_revision(observed_revision))
        heartbeat_wait = asyncio.create_task(asyncio.sleep(KEEPALIVE_INTERVAL))
        cancel_wait = asyncio.create_task(cancel_event.wait())
        try:
            done, _pending = await asyncio.wait(
                [change_wait, heartbeat_wait, cancel_wait],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_wait in done:
                if run.task is not None and not run.task.done():
                    run.task.cancel()
                    await asyncio.gather(run.task, return_exceptions=True)
                await _safe_write_sse(response, "error", {"reason": "draining"})
                return
            if heartbeat_wait in done:
                if not await _safe_write_sse_comment(response, "heartbeat"):
                    return
        finally:
            for pending in (change_wait, heartbeat_wait, cancel_wait):
                if not pending.done():
                    pending.cancel()
            await asyncio.gather(
                change_wait, heartbeat_wait, cancel_wait, return_exceptions=True
            )


async def post_ask(request: web.Request) -> web.StreamResponse:
    """POST /api/v1/vault/{name}/ask — stream SSE chunks from the LLM worker."""
    # Late resolution: daemon module owns the global worker_proxy + DaemonState.
    _daemon = _runtime_daemon_module()

    vault = _resolve_vault(request.match_info["name"])

    body: dict[str, Any] = {}
    if request.body_exists:
        try:
            body = await request.json()
        except Exception:
            raise web.HTTPBadRequest(reason="Invalid JSON body")

    query = body.get("query") or request.rel_url.query.get("query", "")
    context = body.get("context") or ""
    if not isinstance(context, str):
        context = json.dumps(context, ensure_ascii=False)
    ask_session_id = body.get("ask_session_id") or ""
    if not isinstance(ask_session_id, str):
        ask_session_id = str(ask_session_id)
    default_model, default_reasoning_effort = _default_ask_options()
    model = body.get("model") or default_model
    reasoning_effort = body.get("reasoning_effort") or default_reasoning_effort

    if not query:
        raise web.HTTPBadRequest(reason="Field 'query' is required")

    worker_proxy = getattr(_daemon, "worker_proxy", None)
    if worker_proxy is None:
        raise web.HTTPServiceUnavailable(reason="LLM worker not initialized")

    run_id = _ask_run_id(body.get("ask_run_id"))
    task_id = f"http_ask_{uuid.uuid4().hex}"
    run, created = _ASK_RUN_STORE.get_or_create(run_id, task_id)

    if created:
        task = {
            "type": "task",
            "id": task_id,
            "task_type": "ask",
            "query": query,
            "context": context,
            "ask_session_id": ask_session_id,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "env_keys": body.get("env_keys", {}),
            "env": {"PKM_VAULT_DIR": str(vault.path)},
            "cwd": body.get("cwd"),
        }
        run.task = asyncio.create_task(_execute_ask_run(run, worker_proxy, task))

    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await response.prepare(request)

    # ── drain hook ────────────────────────────────────────────────────────
    cancel_event = asyncio.Event()
    gate = getattr(_daemon.DaemonState, "shutdown_gate", None)
    if gate is not None and hasattr(gate, "register_cancel"):
        gate.register_cancel(cancel_event)

    # ── keepalive ─────────────────────────────────────────────────────────
    def _bump() -> None:
        _daemon.DaemonState.last_activity = time.time()

    keepalive_task = asyncio.create_task(
        run_keepalive(_bump, interval=KEEPALIVE_INTERVAL)
    )

    try:
        await _stream_ask_run(response, run, cancel_event)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Error in SSE ask handler")
        await _safe_write_sse(response, "error", {"message": str(exc)})
    finally:
        keepalive_task.cancel()
        await asyncio.gather(keepalive_task, return_exceptions=True)
        try:
            await response.write_eof()
        except Exception:
            pass

    return response
