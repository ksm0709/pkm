"""F4-8 perf smoke: P99 latency on /notes while an ask-stream is in flight.

Strategy:
  1. Boot an aiohttp test server on a fixed loopback port.
  2. Start a long-running fake ask SSE in the background (mirrors the worker
     mock pattern from test_web_ask_sse.py).
  3. Concurrently hammer GET /api/v1/vault/test-vault/notes with `hey`
     (preferred) or `xargs -P50 curl` fallback.
  4. Parse the P99 latency line and assert P99 < 200ms.

Skips gracefully when neither `hey` nor `curl` are on PATH.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import socket
import subprocess
import time
from typing import Any

import aiohttp
import pytest
from aiohttp.test_utils import TestServer

from pkm import daemon as _daemon
from pkm.config import VaultConfig, WebConfig
from pkm.web.server import make_app
from pkm.web.shutdown import ShutdownGate

TOKEN = "test-perf-token-f48"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _SlowAskWorker:
    """Worker that streams forever until cancelled — keeps SSE busy."""

    def __init__(self) -> None:
        self.pending_tasks: dict[str, Any] = {}
        self.stream_callbacks: dict[str, Any] = {}

    async def send_task(self, task: dict, stream_callback=None) -> dict:
        task_id = task["id"]
        self.pending_tasks[task_id] = asyncio.get_event_loop().create_future()
        try:
            for _ in range(1000):
                if stream_callback:
                    await stream_callback(
                        {
                            "type": "stream",
                            "id": task_id,
                            "chunk": {"type": "content", "content": "."},
                        }
                    )
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            raise
        return {"type": "result", "id": task_id, "data": {"response": "done"}}


def _parse_p99_seconds(stdout: str) -> float | None:
    """Parse `hey` stdout for the '99% in X.XXXX secs' line."""
    m = re.search(r"99%\s+in\s+([\d.]+)\s+secs", stdout)
    if m:
        return float(m.group(1))
    # Some hey versions: "  99% in 0.0123 secs" inside Latency distribution.
    m = re.search(r"99% in ([\d.]+) secs", stdout)
    return float(m.group(1)) if m else None


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=_free_port(), bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def patch_daemon(monkeypatch):
    class _State:
        last_activity = time.time()
        graph_ready = False
        shutdown_gate: ShutdownGate | None = None
        web_runner = None

    monkeypatch.setattr(_daemon, "DaemonState", _State)
    monkeypatch.setattr(_daemon, "worker_proxy", None)
    yield _State


@pytest.mark.anyio
@pytest.mark.skipif(
    shutil.which("hey") is None and shutil.which("curl") is None,
    reason="neither `hey` nor `curl` available on PATH",
)
async def test_p99_under_200ms_during_ask_stream(
    web_cfg: WebConfig, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    monkeypatch.setattr(_daemon, "worker_proxy", _SlowAskWorker())

    app = make_app(web_config=web_cfg)
    server = TestServer(app, port=web_cfg.port)
    await server.start_server()
    try:
        base = f"http://127.0.0.1:{web_cfg.port}"
        notes_url = f"{base}/api/v1/vault/test-vault/notes"

        # Kick off a long ask stream in the background via direct HTTP.
        # We use a raw asyncio task to avoid blocking and to ensure the
        # worker is actively streaming during the perf run.
        async def _drive_ask() -> None:
            import aiohttp

            try:
                async with aiohttp.ClientSession() as sess:
                    async with sess.post(
                        f"{base}/api/v1/vault/test-vault/ask",
                        json={"query": "long"},
                        headers={"Authorization": f"Bearer {TOKEN}"},
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        async for _ in resp.content.iter_chunked(64):
                            pass
            except Exception:
                pass

        ask_task = asyncio.create_task(_drive_ask())
        # Give the SSE handler a beat to attach.
        await asyncio.sleep(0.2)

        loop = asyncio.get_event_loop()
        if shutil.which("hey"):
            cmd = [
                "hey",
                "-n",
                "200",
                "-c",
                "50",
                "-m",
                "GET",
                "-H",
                f"Authorization: Bearer {TOKEN}",
                notes_url,
            ]
            proc = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=60),
            )
            stdout = proc.stdout + proc.stderr
            p99 = _parse_p99_seconds(stdout)
            assert p99 is not None, f"could not parse P99 from hey output:\n{stdout}"
            assert p99 < 0.200, f"P99 {p99:.4f}s ≥ 0.200s\n{stdout}"
        else:
            # Fallback: in-process aiohttp concurrent fetcher.
            # Curl/xargs adds 50–100ms per-spawn overhead that dominates the
            # P99 — using aiohttp directly measures the server, not the shell.
            sem = asyncio.Semaphore(50)
            samples: list[float] = []

            async def _one(sess: aiohttp.ClientSession) -> None:
                async with sem:
                    t0 = time.perf_counter()
                    async with sess.get(
                        notes_url,
                        headers={"Authorization": f"Bearer {TOKEN}"},
                    ) as r:
                        await r.read()
                    samples.append(time.perf_counter() - t0)

            async with aiohttp.ClientSession() as sess:
                await asyncio.gather(*[_one(sess) for _ in range(200)])

            samples.sort()
            idx = max(0, int(round(0.99 * len(samples))) - 1)
            p99 = samples[idx]
            assert p99 < 0.200, f"in-process P99 {p99:.4f}s ≥ 0.200s"

        ask_task.cancel()
        try:
            await ask_task
        except (asyncio.CancelledError, Exception):
            pass
    finally:
        await server.close()
