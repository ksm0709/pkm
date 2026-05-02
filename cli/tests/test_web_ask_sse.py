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
import time
from typing import Any

import pytest
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

    async def send_task(self, task: dict, stream_callback=None) -> dict:
        task_id = task["id"]
        self.task_ids_seen.append(task_id)
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
    yield _State


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
