"""Scenario tests for daemon socket protocol handlers and helper loops."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from types import SimpleNamespace

import pytest

from pkm.config import VaultConfig
from pkm.search_engine import SearchResult


class FakeReader:
    def __init__(self, payload: dict | bytes | None):
        self.payload = payload

    async def readline(self) -> bytes:
        if self.payload is None:
            return b""
        if isinstance(self.payload, bytes):
            return self.payload
        return (json.dumps(self.payload) + "\n").encode("utf-8")


class FakeWriter:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.closed = False
        self.drained = 0

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    async def drain(self) -> None:
        self.drained += 1

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None

    @property
    def text(self) -> str:
        return b"".join(self.chunks).decode("utf-8")

    @property
    def json_lines(self) -> list[dict]:
        return [json.loads(line) for line in self.text.splitlines() if line.strip()]


@pytest.mark.anyio
async def test_handle_client_search_protocol_success_and_fallbacks(
    tmp_vault: VaultConfig, monkeypatch
) -> None:
    """Search requests handle empty/no-vault/missing-index/success responses."""
    import pkm.daemon as daemon

    empty_writer = FakeWriter()
    await daemon.handle_client(
        FakeReader({"action": "search", "query": ""}), empty_writer
    )
    assert empty_writer.text == "[]\n"
    assert empty_writer.closed is True

    no_vault_writer = FakeWriter()
    monkeypatch.setattr(daemon, "resolve_search_vault", lambda vault_name: None)
    await daemon.handle_client(
        FakeReader({"action": "search", "query": "missing vault"}), no_vault_writer
    )
    assert no_vault_writer.text == "[]\n"

    monkeypatch.setattr(daemon, "resolve_search_vault", lambda vault_name: tmp_vault)

    async def missing_index(**kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(daemon, "run_in_process_search", missing_index)
    missing_index_writer = FakeWriter()
    await daemon.handle_client(
        FakeReader({"action": "search", "query": "no index"}), missing_index_writer
    )
    assert missing_index_writer.text == "[]\n"

    result = SearchResult(
        note_id="n1",
        title="Result",
        score=0.9,
        backlink_count=2,
        tags=["tag"],
        rank=1,
        memory_type="semantic",
        importance=7.0,
        path="notes/n1.md",
    )

    async def successful_search(**kwargs):
        assert kwargs["top"] == 3
        assert kwargs["min_importance"] == 5.0
        assert kwargs["memory_type"] == "semantic"
        assert kwargs["recency_weight"] == 0.2
        return [result], None

    daemon.DaemonState.graph_ready = True
    monkeypatch.setattr(daemon, "run_in_process_search", successful_search)
    success_writer = FakeWriter()
    await daemon.handle_client(
        FakeReader(
            {
                "action": "search",
                "query": "topic",
                "top_n": 3,
                "min_importance": 5.0,
                "memory_type_filter": "semantic",
                "recency_weight": 0.2,
            }
        ),
        success_writer,
    )

    payload = success_writer.json_lines[0]
    assert payload["graph_ready"] is True
    assert payload["results"][0]["note_id"] == "n1"
    assert payload["results"][0]["importance"] == 7.0


@pytest.mark.anyio
async def test_handle_client_index_reload_and_queue_task_paths(
    tmp_vault: VaultConfig, monkeypatch
) -> None:
    """Index and queue actions return protocol responses without real daemon state."""
    import pkm.daemon as daemon

    monkeypatch.setattr(daemon, "discover_vaults", lambda: {})
    no_vault_writer = FakeWriter()
    await daemon.handle_client(
        FakeReader({"action": "update_index", "vault_name": "missing"}), no_vault_writer
    )
    assert no_vault_writer.json_lines == [{"error": "vault not found"}]

    run_calls: list[tuple[str, object]] = []

    class InlineLoop:
        def run_in_executor(self, executor, fn, arg):
            run_calls.append((fn.__name__, arg))
            fn(arg)
            future = asyncio.Future()
            future.set_result(None)
            return future

    monkeypatch.setattr(daemon.asyncio, "get_running_loop", lambda: InlineLoop())
    monkeypatch.setattr(daemon, "discover_vaults", lambda: {"vault": tmp_vault})
    monkeypatch.setattr("pkm.search_engine.build_index", lambda vault: None)
    monkeypatch.setattr(daemon, "_reload_vault_caches", lambda vault: None)

    update_writer = FakeWriter()
    await daemon.handle_client(FakeReader({"action": "update_index"}), update_writer)
    assert update_writer.json_lines == [{"status": "ok"}]
    assert run_calls[0][0] == "_bg_update"

    reload_writer = FakeWriter()
    await daemon.handle_client(FakeReader({"action": "RELOAD_INDEX"}), reload_writer)
    assert reload_writer.json_lines == [{"status": "ok"}]
    assert run_calls[-1][0] == "<lambda>"

    monkeypatch.setattr(daemon, "task_queue", None)
    no_queue_writer = FakeWriter()
    await daemon.handle_client(FakeReader({"action": "queue_task"}), no_queue_writer)
    assert no_queue_writer.json_lines == [{"error": "Task queue not initialized"}]

    class Queue:
        def __init__(self):
            self.pushed: list[dict] = []

        def push(self, task):
            self.pushed.append(task)

    queue = Queue()
    monkeypatch.setattr(daemon, "task_queue", queue)
    missing_task_writer = FakeWriter()
    await daemon.handle_client(
        FakeReader({"action": "queue_task"}), missing_task_writer
    )
    assert missing_task_writer.json_lines == [{"error": "missing task"}]

    queued_writer = FakeWriter()
    await daemon.handle_client(
        FakeReader({"action": "queue_task", "task": {"id": "t1"}}), queued_writer
    )
    assert queued_writer.json_lines == [{"status": "queued"}]
    assert queue.pushed == [{"id": "t1"}]


@pytest.mark.anyio
async def test_handle_client_ask_builds_context_streams_and_reports_worker_errors(
    tmp_vault: VaultConfig, monkeypatch
) -> None:
    """Ask requests build note context, forward stream chunks, and surface worker errors."""
    import pkm.daemon as daemon

    monkeypatch.setattr(daemon, "worker_proxy", None)
    no_worker_writer = FakeWriter()
    await daemon.handle_client(FakeReader({"action": "ask"}), no_worker_writer)
    assert no_worker_writer.json_lines == [{"error": "LLM worker not initialized"}]

    index_path = tmp_vault.pkm_dir / "index.json"
    index_path.write_text("{}", encoding="utf-8")
    note_path = tmp_vault.notes_dir / "context-note.md"
    note_path.write_text(
        "---\nid: context-note\ntitle: Context Note\ntags: [ctx]\n---\n\nContext body.",
        encoding="utf-8",
    )
    graph = __import__("networkx").DiGraph()
    graph.add_node(
        "context-note", type="note", title="Context Note", path=str(note_path)
    )
    graph.add_node("neighbor", type="note", title="Neighbor", path=str(note_path))
    graph.add_edge("context-note", "neighbor")
    graph_path = tmp_vault.pkm_dir / "graph.json"
    graph_path.write_text(
        json.dumps(__import__("networkx").node_link_data(graph)), encoding="utf-8"
    )

    monkeypatch.setattr(daemon, "discover_vaults", lambda: {"vault": tmp_vault})
    monkeypatch.setattr(daemon, "_require_transformers", lambda model: object())
    monkeypatch.setattr(daemon, "get_cached_index", lambda path, mtime: object())
    monkeypatch.setattr(daemon, "_resolve_graph_path", lambda vault, tier: graph_path)
    monkeypatch.setattr(
        daemon,
        "get_cached_graph",
        lambda path, mtime: graph,
    )
    monkeypatch.setattr(
        daemon,
        "search",
        lambda **kwargs: [
            SimpleNamespace(
                note_id="context-note",
                title="Context Note",
                path=str(note_path),
            ),
            SimpleNamespace(
                note_id="context-note",
                title="Duplicate",
                path=str(note_path),
            ),
        ],
    )
    daemon.DaemonState.graph_ready = True

    captured: dict[str, object] = {}

    class Worker:
        async def send_task(self, task, stream_callback=None):
            captured["task"] = task
            assert stream_callback is not None
            await stream_callback({"type": "stream", "id": task["id"], "delta": "hi"})
            return {"type": "result", "id": task["id"], "answer": "done"}

    monkeypatch.setattr(daemon, "worker_proxy", Worker())
    ask_writer = FakeWriter()
    await daemon.handle_client(
        FakeReader(
            {
                "action": "ask",
                "query": "context",
                "vault_name": "vault",
                "graph_depth": 1,
                "env_keys": {"API_TOKEN": "x"},
                "env": {"EXTRA_ENV": "y"},
                "model": "custom",
                "reasoning_effort": "low",
                "cwd": "/tmp/work",
            }
        ),
        ask_writer,
    )

    lines = ask_writer.json_lines
    assert lines[0]["type"] == "stream"
    assert lines[1]["type"] == "result"
    task = captured["task"]
    assert isinstance(task, dict)
    assert task["model"] == "custom"
    assert task["reasoning_effort"] == "low"
    assert task["env"]["PKM_VAULT_DIR"] == str(tmp_vault.path)
    assert "Context body." in task["context"]
    assert "Metadata:" in task["context"]

    class FailingWorker:
        async def send_task(self, task, stream_callback=None):
            raise RuntimeError("worker failed")

    monkeypatch.setattr(daemon, "worker_proxy", FailingWorker())
    error_writer = FakeWriter()
    await daemon.handle_client(
        FakeReader({"action": "ask", "query": "q"}), error_writer
    )
    assert error_writer.json_lines == [{"error": "worker failed"}]


@pytest.mark.anyio
async def test_process_background_tasks_handles_success_budget_and_task_errors(
    monkeypatch,
) -> None:
    """Background task loop pops queued work, pauses on budgets, and survives errors."""
    import pkm.daemon as daemon

    class Queue:
        def __init__(self, tasks):
            self.tasks = list(tasks)
            self.popped: list[dict] = []

        def peek(self):
            return self.tasks[0] if self.tasks else None

        def pop(self):
            if not self.tasks:
                return None
            task = self.tasks.pop(0)
            self.popped.append(task)
            return task

    class Budget:
        def __init__(self, failures=0):
            self.failures = failures

        def check_and_consume(self, tokens):
            if self.failures:
                self.failures -= 1
                raise daemon.BudgetExhausted("budget")

    class Worker:
        def __init__(self, failures=0):
            self.budget = Budget()
            self.failures = failures
            self.sent: list[dict] = []

        async def send_task(self, task):
            if self.failures:
                self.failures -= 1
                raise RuntimeError("send failed")
            self.sent.append(task)

    sleep_calls = 0
    sleep_stop_at = 2

    async def fake_sleep(seconds):
        nonlocal sleep_calls, sleep_stop_at
        sleep_calls += 1
        if sleep_calls >= sleep_stop_at:
            raise asyncio.CancelledError

    monkeypatch.setattr(daemon.asyncio, "sleep", fake_sleep)

    queue = Queue([{"id": "ok"}])
    worker = Worker()
    monkeypatch.setattr(daemon, "task_queue", queue)
    monkeypatch.setattr(daemon, "worker_proxy", worker)
    with pytest.raises(asyncio.CancelledError):
        await daemon.process_background_tasks()
    assert worker.sent == [{"id": "ok"}]
    assert daemon.DaemonState.current_task is None

    sleep_calls = 0
    sleep_stop_at = 1
    budget_queue = Queue([{"id": "budget"}])
    budget_worker = Worker()
    budget_worker.budget = Budget(failures=1)
    monkeypatch.setattr(daemon, "task_queue", budget_queue)
    monkeypatch.setattr(daemon, "worker_proxy", budget_worker)
    with pytest.raises(asyncio.CancelledError):
        await daemon.process_background_tasks()
    assert budget_queue.popped == []

    sleep_calls = 0
    sleep_stop_at = 2
    failing_queue = Queue([{"id": "bad"}])
    failing_worker = Worker(failures=1)
    monkeypatch.setattr(daemon, "task_queue", failing_queue)
    monkeypatch.setattr(daemon, "worker_proxy", failing_worker)
    with pytest.raises(asyncio.CancelledError):
        await daemon.process_background_tasks()
    assert failing_queue.popped == [{"id": "bad"}]
    assert daemon.DaemonState.current_task is None


def test_graph_cache_reload_and_preload_helpers(
    tmp_vault: VaultConfig, monkeypatch
) -> None:
    """Graph helper paths cover enriched fallback, load failures, preload, and reload."""
    import networkx as nx
    import pkm.daemon as daemon

    assert (
        daemon._resolve_graph_path(tmp_vault, "structural")
        == tmp_vault.pkm_dir / "graph.json"
    )
    assert (
        daemon._resolve_graph_path(tmp_vault, "enriched")
        == tmp_vault.pkm_dir / "graph.json"
    )

    enriched = tmp_vault.pkm_dir / "graph_enriched.json"
    graph = nx.DiGraph()
    graph.add_node("n")
    enriched.write_text(json.dumps(nx.node_link_data(graph)), encoding="utf-8")
    daemon.get_cached_graph.cache_clear()
    assert daemon._resolve_graph_path(tmp_vault, "enriched") == enriched
    assert daemon.get_cached_graph(str(enriched), enriched.stat().st_mtime).has_node(
        "n"
    )

    missing = tmp_vault.pkm_dir / "missing-graph.json"
    assert daemon.get_cached_graph(str(missing), 0.0) is None

    bad = tmp_vault.pkm_dir / "bad-graph.json"
    bad.write_text("{bad json", encoding="utf-8")
    monkeypatch.setattr(daemon.time, "sleep", lambda seconds: None)
    assert daemon.get_cached_graph(str(bad), bad.stat().st_mtime) is None

    monkeypatch.setattr(daemon, "_require_transformers", lambda model: object())
    monkeypatch.setattr(daemon, "discover_vaults", lambda: {"vault": tmp_vault})
    daemon.DaemonState.graph_ready = False
    daemon._preload_model()
    assert daemon.DaemonState.graph_ready is True

    daemon.DaemonState.graph_ready = True
    daemon._reload_vault_caches(tmp_vault)
    assert daemon.DaemonState.graph_ready is True


class FakeStdout:
    def __init__(self, lines: list[bytes]) -> None:
        self.lines = list(lines)

    async def readline(self) -> bytes:
        if not self.lines:
            return b""
        return self.lines.pop(0)


class FakeStdin:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None

    @property
    def json_lines(self) -> list[dict]:
        return [json.loads(line) for line in b"".join(self.writes).splitlines()]


@pytest.mark.anyio
async def test_worker_stdout_handles_llm_budget_stream_and_results(
    monkeypatch,
) -> None:
    """Worker stdout IPC routes LLM, budget, stream, and completion messages."""
    import pkm.daemon as daemon

    class FakeCompletion:
        choices = [SimpleNamespace(message=SimpleNamespace(content="answer"))]
        usage = SimpleNamespace(total_tokens=2)

    monkeypatch.setitem(
        sys.modules,
        "litellm",
        SimpleNamespace(completion=lambda model, messages: FakeCompletion()),
    )

    stdout = FakeStdout(
        [
            json.dumps(
                {
                    "type": "llm_request",
                    "id": "llm1",
                    "model": "model",
                    "messages": [{"role": "user", "content": "hi"}],
                }
            ).encode()
            + b"\n",
            json.dumps({"type": "token_usage", "tokens": 1_000_000}).encode() + b"\n",
            json.dumps({"type": "stream", "id": "task1", "delta": "chunk"}).encode()
            + b"\n",
            json.dumps({"type": "result", "id": "task1", "value": 42}).encode() + b"\n",
            json.dumps({"type": "error", "id": "task2", "message": "bad"}).encode()
            + b"\n",
        ]
    )
    stdin = FakeStdin()
    proxy = daemon.LLMWorkerProxy()
    proxy.process = SimpleNamespace(stdout=stdout, stdin=stdin)
    proxy.pending_tasks["task1"] = asyncio.Future()
    proxy.pending_tasks["task2"] = asyncio.Future()
    stream_messages: list[dict] = []

    async def on_stream(msg):
        stream_messages.append(msg)

    proxy.stream_callbacks["task1"] = on_stream

    await proxy._handle_worker_stdout()

    writes = stdin.json_lines
    assert writes[0] == {"type": "llm_response", "id": "llm1", "content": "answer"}
    assert writes[1] == {"type": "abort"}
    assert stream_messages == [{"type": "stream", "id": "task1", "delta": "chunk"}]
    assert proxy.pending_tasks == {}
    assert proxy.stream_callbacks == {}


@pytest.mark.anyio
async def test_worker_stdout_reports_llm_errors_and_budget_exhaustion(
    monkeypatch,
) -> None:
    """LLM failures and response-token overages are sent back as llm_error IPC."""
    import pkm.daemon as daemon

    class ExpensiveCompletion:
        choices = [SimpleNamespace(message=SimpleNamespace(content="answer"))]
        usage = SimpleNamespace(total_tokens=10)

    stdin = FakeStdin()
    proxy = daemon.LLMWorkerProxy()
    proxy.budget = daemon.TokenBudget(max_tokens=1, window_seconds=60)
    proxy.process = SimpleNamespace(
        stdout=FakeStdout(
            [
                json.dumps({"type": "llm_request", "id": "budget"}).encode() + b"\n",
                json.dumps({"type": "llm_request", "id": "boom"}).encode() + b"\n",
            ]
        ),
        stdin=stdin,
    )
    calls = 0

    def fake_completion(model, messages):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ExpensiveCompletion()
        raise RuntimeError("provider down")

    monkeypatch.setitem(
        sys.modules, "litellm", SimpleNamespace(completion=fake_completion)
    )

    await proxy._handle_worker_stdout()

    writes = stdin.json_lines
    assert writes[0]["type"] == "llm_error"
    assert writes[0]["id"] == "budget"
    assert "Token budget exhausted" in writes[0]["message"]
    assert writes[1] == {
        "type": "llm_error",
        "id": "boom",
        "message": "provider down",
    }


@pytest.mark.anyio
async def test_worker_proxy_send_task_writes_and_resolves_future() -> None:
    """send_task writes JSON IPC, registers stream callbacks, and awaits the result."""
    import pkm.daemon as daemon

    proxy = daemon.LLMWorkerProxy()
    stdin = FakeStdin()
    proxy.process = SimpleNamespace(stdin=stdin)

    async def complete_pending():
        while "task1" not in proxy.pending_tasks:
            await asyncio.sleep(0)
        proxy.pending_tasks["task1"].set_result({"type": "result", "id": "task1"})

    completer = asyncio.create_task(complete_pending())
    result = await proxy.send_task(
        {"id": "task1", "type": "task"}, stream_callback=list
    )
    await completer

    assert stdin.json_lines == [{"id": "task1", "type": "task"}]
    assert proxy.stream_callbacks["task1"] is list
    assert result == {"type": "result", "id": "task1"}


@pytest.mark.anyio
async def test_worker_proxy_send_task_requires_running_stdin() -> None:
    """send_task fails clearly when the worker process is absent."""
    import pkm.daemon as daemon

    with pytest.raises(RuntimeError, match="Worker not running"):
        await daemon.LLMWorkerProxy().send_task({"id": "task1"})


@pytest.mark.anyio
async def test_worker_stderr_logging_redacts_secret_lines(caplog) -> None:
    """Worker stderr is logged with token/key material redacted."""
    import pkm.daemon as daemon

    caplog.set_level(logging.INFO, logger="pkm.daemon")
    proxy = daemon.LLMWorkerProxy()
    proxy.process = SimpleNamespace(
        stderr=FakeStdout([b"api token leaked\n", b"normal warning\n"])
    )

    await proxy._log_stderr()

    assert "[Worker STDERR] <REDACTED>" in caplog.text
    assert "[Worker STDERR] normal warning" in caplog.text


@pytest.mark.anyio
async def test_handle_client_empty_and_invalid_requests_are_safe() -> None:
    """Empty and malformed socket requests close cleanly with internal error payloads."""
    import pkm.daemon as daemon

    empty_writer = FakeWriter()
    await daemon.handle_client(FakeReader(None), empty_writer)
    assert empty_writer.text == ""
    assert empty_writer.closed is True

    bad_writer = FakeWriter()
    await daemon.handle_client(FakeReader(b"{bad json\n"), bad_writer)
    assert bad_writer.json_lines == [{"error": "internal"}]


@pytest.mark.anyio
async def test_idle_checker_closes_server_after_timeout(monkeypatch) -> None:
    """Idle checker closes the server when activity is older than the timeout."""
    import pkm.daemon as daemon

    class Server:
        closed = False

        def close(self):
            self.closed = True

    async def fake_sleep(seconds):
        return None

    server = Server()
    monkeypatch.delenv(daemon.KEEPALIVE_ENV, raising=False)
    monkeypatch.setattr(daemon.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(daemon.time, "time", lambda: 10_000)
    daemon.DaemonState.last_activity = 0

    await daemon.idle_checker(server)

    assert server.closed is True
