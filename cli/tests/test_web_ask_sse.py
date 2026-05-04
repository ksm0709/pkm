"""Integration tests: SSE ask route (B9 / B11).

Coverage:
  (a) task-id uniqueness across concurrent requests
  (b) keepalive bumps DaemonState.last_activity periodically
  (c) drain hook cancels stream within 5 s when shutdown_gate fires
  (d) SSE event format: stream / result / error events serialized correctly
  (e) auth via ?token= query param works on /ask (SSE-whitelisted)
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import types
from types import SimpleNamespace
from typing import Any

import pytest
from aiohttp.client_exceptions import ClientConnectionResetError
from aiohttp.test_utils import TestClient, TestServer

from pkm import daemon as _daemon
from pkm.config import VaultConfig, WebConfig
from pkm.web import routes as _routes_pkg  # noqa: F401  (forces import side-effects)
from pkm.web.routes import ask as ask_route
from pkm.web.server import make_app
from pkm.web.shutdown import ShutdownGate

TOKEN = "test-ask-sse-token-b11"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7430, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def app(web_cfg: WebConfig):
    return make_app(web_config=web_cfg)


class _FakeWorker:
    """Stand-in for ``LLMWorkerProxy`` that emits scripted chunks."""

    def __init__(
        self,
        chunks: list[dict] | None = None,
        result: dict | None = None,
        pre_result_delay: float = 0.0,
    ) -> None:
        self.pending_tasks: dict[str, Any] = {}
        self.stream_callbacks: dict[str, Any] = {}
        self.chunks = chunks or []
        self.result = result or {
            "type": "result",
            "id": "",
            "status": "success",
            "data": {"response": "ok"},
        }
        self.pre_result_delay = pre_result_delay
        self.task_ids_seen: list[str] = []
        self.tasks_seen: list[dict[str, Any]] = []

    async def send_task(self, task: dict, stream_callback=None) -> dict:
        task_id = task["id"]
        self.task_ids_seen.append(task_id)
        self.tasks_seen.append(task)
        self.pending_tasks[task_id] = asyncio.get_event_loop().create_future()
        if stream_callback:
            self.stream_callbacks[task_id] = stream_callback
            for chunk in self.chunks:
                await stream_callback({"type": "stream", "id": task_id, "chunk": chunk})
        if self.pre_result_delay:
            await asyncio.sleep(self.pre_result_delay)
        self.pending_tasks.pop(task_id, None)
        self.stream_callbacks.pop(task_id, None)
        return {**self.result, "id": task_id}


class _HangingWorker:
    """Worker whose ``send_task`` blocks forever — used for drain tests."""

    def __init__(self) -> None:
        self.pending_tasks: dict[str, Any] = {}
        self.stream_callbacks: dict[str, Any] = {}
        self.cancelled = asyncio.Event()

    async def send_task(self, task: dict, stream_callback=None) -> dict:
        task_id = task["id"]
        self.pending_tasks[task_id] = asyncio.get_event_loop().create_future()
        if stream_callback:
            self.stream_callbacks[task_id] = stream_callback
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return {"type": "result", "id": task_id, "data": {"response": ""}}


@pytest.fixture
def patch_daemon(monkeypatch):
    """Reset daemon globals + install a fake DaemonState with isolated state."""

    class _State:
        last_activity = time.time()
        graph_ready = False
        shutdown_gate: ShutdownGate | None = None
        web_runner = None

    monkeypatch.setattr(_daemon, "DaemonState", _State)
    monkeypatch.setattr(_daemon, "worker_proxy", None)
    ask_route._ASK_RUN_STORE.runs.clear()
    yield _State
    ask_route._ASK_RUN_STORE.runs.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sse(text: str) -> list[dict]:
    """Parse an SSE response body into a list of ``{event, data}`` dicts."""
    events: list[dict] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        evt = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                evt = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if not data_lines:
            continue
        try:
            data = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            data = {"_raw": "\n".join(data_lines)}
        events.append({"event": evt, "data": data})
    return events


class _ClosingResponse:
    async def write(self, _data: bytes) -> None:
        raise ClientConnectionResetError("Cannot write to closing transport")


@pytest.mark.anyio
async def test_safe_sse_write_treats_client_disconnect_as_closed() -> None:
    """Mobile/browser disconnects should not be logged as ask handler failures."""
    wrote = await ask_route._safe_write_sse(
        _ClosingResponse(), "result", {"response": "late"}
    )

    assert wrote is False


@pytest.mark.anyio
async def test_stream_client_disconnect_does_not_cancel_background_ask_run() -> None:
    """A backgrounded mobile tab can drop SSE while the agent should continue."""
    run = ask_route.AskRun(
        run_id="web-run-disconnect",
        task_id="http_ask_disconnect",
        created_at=time.time(),
        updated_at=time.time(),
    )
    await run.append_chunk("content", {"type": "content", "content": "still running"})
    run.task = asyncio.create_task(asyncio.Event().wait())

    await ask_route._stream_ask_run(_ClosingResponse(), run, asyncio.Event())

    assert run.task is not None
    assert not run.task.done()
    run.task.cancel()
    await asyncio.gather(run.task, return_exceptions=True)


# ---------------------------------------------------------------------------
# (a) task-id uniqueness
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_task_ids_unique_across_concurrent_requests(
    app, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    """50 concurrent ask requests must each receive a unique task_id."""
    fake = _FakeWorker(
        chunks=[{"type": "content", "content": "hi"}],
        result={"type": "result", "data": {"response": "hi"}},
    )
    monkeypatch.setattr(_daemon, "worker_proxy", fake)

    async with TestClient(TestServer(app)) as client:

        async def _one_call() -> int:
            resp = await client.post(
                "/api/v1/vault/test-vault/ask",
                json={"query": "hello"},
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
            await resp.text()
            return resp.status

        statuses = await asyncio.gather(*[_one_call() for _ in range(50)])

    assert all(s == 200 for s in statuses), statuses
    assert len(fake.task_ids_seen) == 50
    assert len(set(fake.task_ids_seen)) == 50, "task_ids collided"
    for tid in fake.task_ids_seen:
        assert tid.startswith("http_ask_"), tid


@pytest.mark.anyio
async def test_post_ask_forwards_body_context_to_worker_task(
    app, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    """HTTP ask must pass frontend session identity and transcript to the worker."""
    fake = _FakeWorker(result={"type": "result", "data": {"response": "ok"}})
    monkeypatch.setattr(_daemon, "worker_proxy", fake)

    context = "Previous ask session transcript:\n\nUser: first\nAssistant: answer"
    ask_session_id = "web-alpha-test-session"

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={
                "query": "follow up",
                "context": context,
                "ask_session_id": ask_session_id,
            },
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        await resp.text()

    assert resp.status == 200
    assert fake.tasks_seen
    assert fake.tasks_seen[0]["query"] == "follow up"
    assert fake.tasks_seen[0]["context"] == context
    assert fake.tasks_seen[0]["ask_session_id"] == ask_session_id


@pytest.mark.anyio
async def test_ask_run_status_returns_cached_chunks_and_result(
    app, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    """A completed ask run should be recoverable after the browser stream dies."""
    fake = _FakeWorker(
        chunks=[
            {"type": "reasoning", "content": "thinking"},
            {"type": "content", "content": "answer"},
        ],
        result={"type": "result", "data": {"response": "answer"}},
    )
    monkeypatch.setattr(_daemon, "worker_proxy", fake)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={"query": "recover me", "ask_run_id": "web-run-recover"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        await resp.text()

        status_resp = await client.get(
            "/api/v1/vault/test-vault/ask/runs/web-run-recover",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        status = await status_resp.json()

    assert status_resp.status == 200
    assert status["run_id"] == "web-run-recover"
    assert status["status"] == "done"
    assert status["result"] == {"response": "answer"}
    assert [chunk["event"] for chunk in status["chunks"]] == ["reasoning", "content"]
    assert status["chunks"][1]["data"]["content"] == "answer"


@pytest.mark.anyio
async def test_reusing_ask_run_id_does_not_start_duplicate_worker_task(
    app, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    """A reconnect with the same ask_run_id must attach to the existing run."""
    fake = _FakeWorker(
        chunks=[{"type": "content", "content": "cached"}],
        result={"type": "result", "data": {"response": "cached"}},
    )
    monkeypatch.setattr(_daemon, "worker_proxy", fake)

    async with TestClient(TestServer(app)) as client:
        first = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={"query": "one", "ask_run_id": "web-run-dedupe"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        await first.text()

        second = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={"query": "one", "ask_run_id": "web-run-dedupe"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        second_body = await second.text()

    assert first.status == 200
    assert second.status == 200
    assert len(fake.tasks_seen) == 1
    events = _parse_sse(second_body)
    assert events[-1] == {"event": "result", "data": {"response": "cached"}}


# ---------------------------------------------------------------------------
# (b) keepalive bumps last_activity
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_keepalive_bumps_last_activity(
    app, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    """While a slow ask is in flight, the keepalive helper must refresh
    ``DaemonState.last_activity`` at least once."""
    monkeypatch.setattr(ask_route, "KEEPALIVE_INTERVAL", 0.05)
    fake = _FakeWorker(
        chunks=[{"type": "content", "content": "slow"}],
        result={"type": "result", "data": {"response": "slow"}},
        pre_result_delay=0.4,  # >> KEEPALIVE_INTERVAL → multiple bumps expected
    )
    monkeypatch.setattr(_daemon, "worker_proxy", fake)

    # Freeze the entry baseline well in the past so any bump produces a delta
    # the assertion can detect.
    patch_daemon.last_activity = 0.0
    baseline = patch_daemon.last_activity

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={"query": "slow"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        await resp.text()
        assert resp.status == 200

    # last_activity must have been bumped at least once during the slow ask.
    assert patch_daemon.last_activity > baseline, (
        f"keepalive never fired — last_activity {patch_daemon.last_activity} "
        f"≤ baseline {baseline}"
    )


@pytest.mark.anyio
async def test_ask_stream_sends_browser_heartbeat_while_worker_is_silent(
    app, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    """Long silent agent turns must still send bytes to the browser/proxy."""
    monkeypatch.setattr(ask_route, "KEEPALIVE_INTERVAL", 0.05)
    fake = _FakeWorker(
        chunks=[],
        result={"type": "result", "data": {"response": "slow done"}},
        pre_result_delay=0.18,
    )
    monkeypatch.setattr(_daemon, "worker_proxy", fake)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={"query": "silent slow ask"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        body = await resp.text()

    assert resp.status == 200
    assert ": heartbeat" in body
    events = _parse_sse(body)
    assert events[-1] == {"event": "result", "data": {"response": "slow done"}}


# ---------------------------------------------------------------------------
# (c) drain hook cancels stream within 5 s
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_drain_hook_cancels_stream_within_5s(
    web_cfg: WebConfig, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    """When shutdown_gate.cancel_all() fires, the SSE response must emit
    ``event: error\\ndata: {"reason": "draining"}`` and close in <5 s."""
    gate = ShutdownGate()
    patch_daemon.shutdown_gate = gate

    hanging = _HangingWorker()
    monkeypatch.setattr(_daemon, "worker_proxy", hanging)

    app = make_app(web_config=web_cfg, gate=gate)

    async with TestClient(TestServer(app)) as client:
        request_task = asyncio.create_task(
            client.post(
                "/api/v1/vault/test-vault/ask",
                json={"query": "drain me"},
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
        )

        # Wait until the worker has actually started — i.e. registered a cancel event.
        for _ in range(100):
            if gate._cancel_events:
                break
            await asyncio.sleep(0.02)
        else:
            request_task.cancel()
            pytest.fail("SSE handler never registered a cancel event with the gate")

        t0 = time.monotonic()
        gate.cancel_all()

        resp = await asyncio.wait_for(request_task, timeout=5.0)
        body = await resp.text()
        elapsed = time.monotonic() - t0

    assert elapsed < 5.0, f"drain took {elapsed:.2f}s (>= 5s)"
    assert resp.status == 200
    events = _parse_sse(body)
    drain_events = [e for e in events if e["event"] == "error"]
    assert drain_events, f"no error event in body: {body!r}"
    assert any(e["data"].get("reason") == "draining" for e in drain_events), (
        f"no draining event: {drain_events}"
    )
    assert hanging.cancelled.is_set(), "hanging worker task was never cancelled"


# ---------------------------------------------------------------------------
# (d) SSE event format
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_sse_event_format(
    app, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    """Each worker chunk → one SSE event named after chunk['type']; final
    ``event: result`` carries the worker's ``data`` dict."""
    fake = _FakeWorker(
        chunks=[
            {"type": "tool_detail", "name": "search_notes", "arguments": {"q": "x"}},
            {"type": "reasoning", "content": "thinking..."},
            {"type": "content", "content": "the answer is 42"},
        ],
        result={
            "type": "result",
            "status": "success",
            "data": {"response": "the answer is 42"},
        },
    )
    monkeypatch.setattr(_daemon, "worker_proxy", fake)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={"query": "what is 6*7?"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        assert resp.headers.get("Content-Type", "").startswith("text/event-stream")
        body = await resp.text()

    events = _parse_sse(body)
    event_names = [e["event"] for e in events]
    assert event_names == ["tool_detail", "reasoning", "content", "result"], event_names

    # Stream chunks carry the full chunk dict.
    assert events[0]["data"]["name"] == "search_notes"
    assert events[0]["data"]["arguments"] == {"q": "x"}
    assert events[1]["data"]["content"] == "thinking..."
    assert events[2]["data"]["content"] == "the answer is 42"
    # Final result carries the worker's data dict.
    assert events[3]["data"] == {"response": "the answer is 42"}


@pytest.mark.anyio
async def test_sse_worker_error_emits_error_event(
    app, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    """A worker error result must surface as ``event: error``."""
    fake = _FakeWorker(
        chunks=[],
        result={"type": "error", "message": "model exploded"},
    )
    monkeypatch.setattr(_daemon, "worker_proxy", fake)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={"query": "boom"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        body = await resp.text()
        assert resp.status == 200

    events = _parse_sse(body)
    assert events[-1]["event"] == "error"
    assert events[-1]["data"].get("message") == "model exploded"


@pytest.mark.anyio
async def test_missing_query_returns_400(
    app, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    """Empty/absent ``query`` → 400."""
    monkeypatch.setattr(_daemon, "worker_proxy", _FakeWorker())
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 400


@pytest.mark.anyio
async def test_worker_unavailable_returns_503(
    app, tmp_vault: VaultConfig, patch_daemon
) -> None:
    """When the daemon worker_proxy is None → 503."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={"query": "anything"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 503


@pytest.mark.anyio
async def test_ask_uses_main_module_worker_when_daemon_runs_with_dash_m(
    app, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    """When started as ``python -m pkm.daemon``, runtime globals live on
    ``__main__``.  The web route must use that module instead of importing a
    second ``pkm.daemon`` module whose worker_proxy is still None."""
    monkeypatch.setattr(_daemon, "worker_proxy", None)

    main_mod = types.ModuleType("__main__")
    main_mod.__spec__ = SimpleNamespace(name="pkm.daemon")
    main_mod.worker_proxy = _FakeWorker(
        chunks=[{"type": "content", "content": "main worker answer"}],
        result={"type": "result", "data": {"response": "main worker answer"}},
    )
    main_mod.DaemonState = patch_daemon
    monkeypatch.setitem(sys.modules, "__main__", main_mod)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={"query": "anything"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        body = await resp.text()

    assert resp.status == 200
    events = _parse_sse(body)
    assert events[-1]["event"] == "result"
    assert events[-1]["data"] == {"response": "main worker answer"}


@pytest.mark.anyio
async def test_ask_defaults_to_auto_model_when_request_has_no_model(
    app, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    """The web ask route must match CLI/MCP defaults and avoid stale preview
    model ids when the UI does not explicitly send a model."""
    fake = _FakeWorker()
    monkeypatch.setattr(_daemon, "worker_proxy", fake)
    monkeypatch.setattr(ask_route, "load_config", lambda: {"defaults": {}})

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={"query": "anything"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        await resp.text()

    assert resp.status == 200
    assert fake.tasks_seen[-1]["model"] == "auto"


@pytest.mark.anyio
async def test_ask_uses_configured_default_model_and_reasoning_effort(
    app, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    """The web ask route should honor the same default model settings as the
    CLI ask command when the request body omits them."""
    fake = _FakeWorker()
    monkeypatch.setattr(_daemon, "worker_proxy", fake)
    monkeypatch.setattr(
        ask_route,
        "load_config",
        lambda: {"defaults": {"model": "test/default-model", "reasoning-effort": "high"}},
    )

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={"query": "anything"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        await resp.text()

    assert resp.status == 200
    assert fake.tasks_seen[-1]["model"] == "test/default-model"
    assert fake.tasks_seen[-1]["reasoning_effort"] == "high"


@pytest.mark.anyio
async def test_get_ask_options_returns_configured_default_model(
    app, tmp_vault: VaultConfig, monkeypatch
) -> None:
    """The web UI needs the same resolved ask defaults that POST /ask uses."""
    monkeypatch.setattr(
        ask_route,
        "load_config",
        lambda: {"defaults": {"model": "test/default-model", "reasoning-effort": "medium"}},
    )

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/ask/options",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        body = await resp.json()

    assert resp.status == 200
    assert body == {"model": "test/default-model", "reasoning_effort": "medium"}


# ---------------------------------------------------------------------------
# (e) auth via ?token= on /ask
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_query_token_accepted_on_ask(
    app, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    """SSE_ROUTES whitelist allows ``?token=`` as auth on the ask route."""
    monkeypatch.setattr(_daemon, "worker_proxy", _FakeWorker())
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/ask",
            params={"token": TOKEN},
            json={"query": "hi"},
        )
        assert resp.status == 200


@pytest.mark.anyio
async def test_missing_auth_returns_401(
    app, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    """No Authorization header and no ``?token=`` → 401."""
    monkeypatch.setattr(_daemon, "worker_proxy", _FakeWorker())
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={"query": "hi"},
        )
        assert resp.status == 401
