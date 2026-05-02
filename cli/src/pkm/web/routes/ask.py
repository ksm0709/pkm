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
import time
import uuid
from typing import Any

from aiohttp import web

from pkm.web.keepalive import run_keepalive
from pkm.web.routes.notes import _resolve_vault

logger = logging.getLogger("pkm.web.ask")


def _sse_event(event: str, data: Any) -> bytes:
    """Encode one SSE event line block."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")


async def post_ask(request: web.Request) -> web.StreamResponse:
    """POST /api/v1/vault/{name}/ask — stream SSE chunks from the LLM worker."""
    # Late import: daemon module owns the global worker_proxy + DaemonState.
    from pkm import daemon as _daemon

    vault = _resolve_vault(request.match_info["name"])

    body: dict[str, Any] = {}
    if request.body_exists:
        try:
            body = await request.json()
        except Exception:
            raise web.HTTPBadRequest(reason="Invalid JSON body")

    query = body.get("query") or request.rel_url.query.get("query", "")
    model = body.get("model")
    reasoning_effort = body.get("reasoning_effort")

    if not query:
        raise web.HTTPBadRequest(reason="Field 'query' is required")

    worker_proxy = getattr(_daemon, "worker_proxy", None)
    if worker_proxy is None:
        raise web.HTTPServiceUnavailable(reason="LLM worker not initialized")

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

    task_id = f"http_ask_{uuid.uuid4().hex}"

    # ── drain hook ────────────────────────────────────────────────────────
    cancel_event = asyncio.Event()
    gate = getattr(_daemon.DaemonState, "shutdown_gate", None)
    if gate is not None and hasattr(gate, "register_cancel"):
        gate.register_cancel(cancel_event)

    # ── keepalive ─────────────────────────────────────────────────────────
    def _bump() -> None:
        _daemon.DaemonState.last_activity = time.time()

    keepalive_task = asyncio.create_task(run_keepalive(_bump, interval=30.0))

    # ── stream callback ───────────────────────────────────────────────────
    async def on_stream(msg: dict) -> None:
        chunk = msg.get("chunk") or {}
        event_name = chunk.get("type") or "stream"
        try:
            await response.write(_sse_event(event_name, chunk))
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        except Exception:
            logger.exception("Failed to write SSE chunk")

    task = {
        "type": "task",
        "id": task_id,
        "task_type": "ask",
        "query": query,
        "context": "",
        "model": model or "gemini/gemini-3.1-flash-preview",
        "reasoning_effort": reasoning_effort,
        "env_keys": body.get("env_keys", {}),
        "env": {"PKM_VAULT_DIR": str(vault.path)},
        "cwd": body.get("cwd"),
    }

    send_task = asyncio.create_task(
        worker_proxy.send_task(task, stream_callback=on_stream)
    )
    cancel_wait = asyncio.create_task(cancel_event.wait())

    try:
        done, _pending = await asyncio.wait(
            [send_task, cancel_wait],
            return_when=asyncio.FIRST_COMPLETED,
        )

        if cancel_wait in done and send_task not in done:
            # Drain triggered before worker finished.
            send_task.cancel()
            await asyncio.gather(send_task, return_exceptions=True)
            # Best-effort: drop dangling worker bookkeeping for this task_id.
            worker_proxy.pending_tasks.pop(task_id, None)
            worker_proxy.stream_callbacks.pop(task_id, None)
            try:
                await response.write(_sse_event("error", {"reason": "draining"}))
            except Exception:
                pass
            return response

        # send_task finished — cancel the cancel-watcher.
        if not cancel_wait.done():
            cancel_wait.cancel()
            await asyncio.gather(cancel_wait, return_exceptions=True)

        result = send_task.result()
        if isinstance(result, dict) and result.get("type") == "error":
            await response.write(
                _sse_event("error", {"message": result.get("message", "")})
            )
        else:
            payload = result.get("data", {}) if isinstance(result, dict) else {}
            await response.write(_sse_event("result", payload))

    except asyncio.CancelledError:
        send_task.cancel()
        await asyncio.gather(send_task, return_exceptions=True)
        raise
    except Exception as exc:
        logger.exception("Error in SSE ask handler")
        try:
            await response.write(_sse_event("error", {"message": str(exc)}))
        except Exception:
            pass
    finally:
        keepalive_task.cancel()
        await asyncio.gather(keepalive_task, return_exceptions=True)
        try:
            await response.write_eof()
        except Exception:
            pass

    return response
