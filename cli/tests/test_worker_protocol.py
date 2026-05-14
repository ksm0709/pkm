from __future__ import annotations

import asyncio
import inspect
import io
import json
import os
import sys
from collections import OrderedDict
from types import SimpleNamespace
from typing import Any

import pytest

from pkm import worker
from pkm.workflows.history import read_workflow_history


def test_handle_ask_prompt_lists_patch_note_as_partial_edit_tool() -> None:
    """Worker prompt steers agents to patch_note for partial note edits."""
    source = inspect.getsource(worker.handle_ask)
    assert "patch_note(note_id, operation, old, new, section, fields)" in source
    assert "partial note edits" in source


def test_handle_ask_prompt_matches_relation_neighbor_tool_contract() -> None:
    """Worker prompt names available relation-aware tools, not stale graph tools."""
    source = inspect.getsource(worker.handle_ask)

    assert "get_graph_context" not in source
    assert "get_note_neighbors(note_id, include_semantic)" in source
    assert "create_daily_subnote(title, content)" in source
    assert "&relation [[target]] - reason" in source
    assert "daily relation markers as promotion candidates only" in source


class _FakeIPC:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self._abort_event = asyncio.Event()

    @property
    def abort_event(self):
        return self._abort_event

    async def send_message(self, msg: dict[str, Any]) -> None:
        self.messages.append(msg)


def test_worker_helper_policies_redact_reasoning_sessions_and_cache(
    monkeypatch,
) -> None:
    """Worker helpers enforce privacy, reasoning kwargs, session ids, and LRU cache."""
    assert worker.reasoning_kwargs("gemini/gemini-3-pro", "medium") == {
        "thinking_level": "high"
    }
    assert worker.reasoning_kwargs("gemini/gemini-3-pro", "low") == {
        "thinking_level": "low"
    }
    assert worker.reasoning_kwargs("openai/o3", "high") == {"reasoning_effort": "high"}
    assert worker.reasoning_kwargs("openai/o3", None) == {}

    assert worker.redact(
        {
            "api_key": "secret",
            "nested": [{"token_value": "secret"}, {"safe": "visible"}],
        }
    ) == {
        "api_key": "<REDACTED>",
        "nested": [{"token_value": "<REDACTED>"}, {"safe": "visible"}],
    }

    assert worker._agent_session_id("ask", "task") == "ask-task"
    assert worker._agent_session_id("ask", "task", "web session/../id") == (
        "ask-web-session-..-id"
    )
    assert worker._agent_session_id("ask", "task", "///") == "ask-task"

    cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
    monkeypatch.setattr(worker, "_ASK_AGENT_CACHE", cache)
    cache["same"] = {"signature": ("old",), "agent": object()}
    assert worker._cached_agent("same", ("new",)) is None
    assert "same" not in cache

    valid_agent = object()
    cache["valid"] = {"signature": ("sig",), "agent": valid_agent}
    assert worker._cached_agent("valid", ("sig",)) is valid_agent

    monkeypatch.setattr(worker, "_ASK_AGENT_CACHE_MAX", 2)
    worker._store_agent("a", ("sig",), object())
    worker._store_agent("b", ("sig",), object())
    worker._store_agent("c", ("sig",), object())
    assert list(cache) == ["b", "c"]


def test_rebuild_workflow_index_runs_in_isolated_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Workflow reindex isolates PyTorch imports from the long-lived worker."""
    vault_root = tmp_path / "vaults"
    vault_path = vault_root / "demo"
    vault_path.mkdir(parents=True)
    calls: list[dict[str, Any]] = []

    def fake_run(cmd: list[str], **kwargs: Any):
        calls.append({"cmd": cmd, **kwargs})
        return worker.subprocess.CompletedProcess(cmd, 0, stdout="indexed", stderr="")

    monkeypatch.setattr(worker.subprocess, "run", fake_run)
    monkeypatch.setattr(worker.sys, "executable", "/python")
    monkeypatch.setenv("PKM_WORKFLOW_INDEX_TIMEOUT", "42")

    worker._rebuild_workflow_index(SimpleNamespace(name="demo", path=vault_path))

    assert calls == [
        {
            "cmd": ["/python", "-m", "pkm", "--vault", "demo", "index"],
            "cwd": str(vault_path),
            "env": {**os.environ, "PKM_VAULTS_ROOT": str(vault_root)},
            "capture_output": True,
            "text": True,
            "timeout": 42,
        }
    ]


def test_rebuild_workflow_index_reports_subprocess_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Workflow history receives the isolated index process error text."""
    vault_path = tmp_path / "demo"
    vault_path.mkdir()

    def fake_run(cmd: list[str], **_kwargs: Any):
        return worker.subprocess.CompletedProcess(
            cmd, 2, stdout="ignored stdout", stderr="index exploded"
        )

    monkeypatch.setattr(worker.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match=r"pkm index failed \(2\): index exploded"):
        worker._rebuild_workflow_index(SimpleNamespace(name="demo", path=vault_path))


@pytest.mark.anyio
async def test_ipc_client_writes_json_and_reads_control_messages(monkeypatch) -> None:
    """IPC read loop handles abort/task/noise/EOF while send writes JSON lines."""
    client = worker.IPCClient()
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)

    await client.send_message({"type": "result", "id": "t1"})
    assert json.loads(stdout.getvalue()) == {"type": "result", "id": "t1"}
    assert client.abort_event is client.abort_event

    task_messages: list[dict[str, Any]] = []

    async def fake_handle_task(msg: dict[str, Any]) -> None:
        task_messages.append(msg)

    monkeypatch.setattr(worker, "handle_task", fake_handle_task)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            "\n".join(
                [
                    json.dumps({"type": "abort"}),
                    json.dumps({"type": "task", "id": "task-1"}),
                    json.dumps({"type": "unknown"}),
                    "{not json",
                    "",
                ]
            )
        ),
    )

    await client.reader_loop()
    await asyncio.sleep(0)

    assert client.abort_event.is_set()
    assert task_messages == [{"type": "task", "id": "task-1"}]


@pytest.mark.anyio
async def test_agent_task_outcome_prefers_turn_stop_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Workflow history should use tiny-agent turn_stop output when available."""
    fake_ipc = _FakeIPC()
    monkeypatch.setattr(worker, "ipc", fake_ipc)
    monkeypatch.delenv("PKM_TEST_MOCK_LLM", raising=False)
    monkeypatch.setattr("pkm.tools.get_pkm_tools", lambda: [])

    import tiny_agent.agent

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            self.hooks = kwargs["hooks"]

        async def run(self, _user_content: str):
            yield {"type": "content", "content": "verbose progress "}
            yield {
                "type": "tool_end",
                "name": "turn_stop",
                "result": {"output": "concise completion summary"},
            }
            yield {"type": "content", "content": "after stop"}

    monkeypatch.setattr(tiny_agent.agent, "Agent", FakeAgent)

    outcome = await worker._run_agent_task_impl(
        task_id="agent-summary",
        session_prefix="pkm-test",
        user_content="question",
        system_prompt="system",
        vault_dir=str(tmp_path),
        model="test/model",
    )

    assert outcome.status == "success"
    assert outcome.response == "verbose progress after stop"
    assert outcome.result_summary == "concise completion summary"
    assert fake_ipc.messages[-1]["data"]["response"] == "verbose progress after stop"


@pytest.mark.anyio
async def test_agent_task_fallback_model_tool_stream_and_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Agent execution falls back to default model and streams tool/content chunks."""
    fake_ipc = _FakeIPC()
    monkeypatch.setattr(worker, "ipc", fake_ipc)
    monkeypatch.delenv("PKM_TEST_MOCK_LLM", raising=False)
    monkeypatch.setattr("pkm.tools.get_pkm_tools", lambda: ["tool"])

    import builtins
    import tiny_agent.agent

    original_import = builtins.__import__

    def import_without_models(name, *args, **kwargs):
        if name == "pkm.models":
            raise ImportError("no models module")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_models)

    created: list[dict[str, Any]] = []

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            self.hooks = kwargs["hooks"]
            created.append(kwargs)

        async def run(self, user_content: str):
            await self.hooks["on_tool_start"]("lookup", {"query": user_content}, self)
            yield {"type": "content", "content": "hello "}
            yield {"type": "content", "content": "world"}

    monkeypatch.setattr(tiny_agent.agent, "Agent", FakeAgent)

    outcome = await worker._run_agent_task_impl(
        task_id="agent-1",
        session_prefix="pkm-test",
        user_content="question",
        system_prompt="system",
        vault_dir=str(tmp_path),
        model=None,
        reasoning_effort="high",
        cwd=str(tmp_path / "cwd"),
        skills_dirs=["skills"],
    )

    agent_kwargs = created[0]
    assert agent_kwargs["model"] == "gemini/gemini-3-flash-preview"
    assert agent_kwargs["tools"] == ["tool"]
    assert agent_kwargs["skills_dirs"] == ["skills"]
    assert agent_kwargs["instruction_dirs"] == [str(tmp_path), str(tmp_path / "cwd")]
    assert agent_kwargs["litellm_kwargs"] == {"thinking_level": "high"}

    assert fake_ipc.messages[0]["chunk"]["type"] == "tool_detail"
    assert fake_ipc.messages[-1] == {
        "type": "result",
        "id": "agent-1",
        "status": "success",
        "data": {"response": "hello world"},
    }
    assert outcome.status == "success"
    assert outcome.result_summary == "hello world"


@pytest.mark.anyio
async def test_agent_task_reused_session_refreshes_hooks_and_clears_tasks(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Persistent ask sessions reuse the agent but reset per-turn task state."""
    fake_ipc = _FakeIPC()
    monkeypatch.setattr(worker, "ipc", fake_ipc)
    monkeypatch.delenv("PKM_TEST_MOCK_LLM", raising=False)
    monkeypatch.setattr(worker, "_ASK_AGENT_CACHE", OrderedDict())
    monkeypatch.setattr("pkm.tools.get_pkm_tools", lambda: [])

    import tiny_agent.agent

    instances: list[FakeAgent] = []

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            self.hooks = kwargs["hooks"]
            self.tasks = [{"status": "stale"}]
            self.task_snapshots: list[list[dict[str, str]]] = []
            instances.append(self)

        async def run(self, user_content: str):
            self.task_snapshots.append(list(self.tasks))
            yield {"type": "content", "content": user_content}

    monkeypatch.setattr(tiny_agent.agent, "Agent", FakeAgent)

    for task_id, content in (("t1", "one"), ("t2", "two")):
        await worker._run_agent_task_impl(
            task_id=task_id,
            session_prefix="pkm-ask",
            user_content=content,
            system_prompt="system",
            vault_dir=str(tmp_path),
            model="test/model",
            persistent_session_id="web-session",
        )

    assert len(instances) == 1
    assert instances[0].task_snapshots == [[], []]
    result_messages = [m for m in fake_ipc.messages if m["type"] == "result"]
    assert [m["data"]["response"] for m in result_messages] == ["one", "two"]


@pytest.mark.anyio
async def test_agent_task_error_chunk_emits_worker_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Agent error chunks are converted to worker IPC error messages."""
    fake_ipc = _FakeIPC()
    monkeypatch.setattr(worker, "ipc", fake_ipc)
    monkeypatch.delenv("PKM_TEST_MOCK_LLM", raising=False)
    monkeypatch.setattr("pkm.tools.get_pkm_tools", lambda: [])

    import tiny_agent.agent

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            self.hooks = kwargs["hooks"]

        async def run(self, _user_content: str):
            yield {"type": "error", "content": "model failed"}

    monkeypatch.setattr(tiny_agent.agent, "Agent", FakeAgent)

    await worker._run_agent_task_impl(
        task_id="err-1",
        session_prefix="pkm-test",
        user_content="question",
        system_prompt="system",
        vault_dir=str(tmp_path),
        model="test/model",
    )

    assert fake_ipc.messages[-1] == {
        "type": "error",
        "id": "err-1",
        "message": "model failed",
    }


@pytest.mark.anyio
async def test_agent_task_abort_cancels_hanging_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Abort signals cancel a running agent and report daemon-aborted status."""
    fake_ipc = _FakeIPC()
    monkeypatch.setattr(worker, "ipc", fake_ipc)
    monkeypatch.delenv("PKM_TEST_MOCK_LLM", raising=False)
    monkeypatch.setattr("pkm.tools.get_pkm_tools", lambda: [])

    import tiny_agent.agent

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            self.hooks = kwargs["hooks"]

        async def run(self, _user_content: str):
            fake_ipc.abort_event.set()
            await asyncio.Event().wait()
            yield {"type": "content", "content": "unreachable"}

    monkeypatch.setattr(tiny_agent.agent, "Agent", FakeAgent)

    await worker._run_agent_task_impl(
        task_id="abort-1",
        session_prefix="pkm-test",
        user_content="question",
        system_prompt="system",
        vault_dir=str(tmp_path),
        model="test/model",
    )

    assert fake_ipc.messages[-1] == {
        "type": "error",
        "id": "abort-1",
        "message": "Task aborted by daemon",
    }


@pytest.mark.anyio
async def test_agent_task_reports_no_auto_models(monkeypatch, tmp_path) -> None:
    """Auto model resolution failure is reported as a worker error."""
    fake_ipc = _FakeIPC()
    monkeypatch.setattr(worker, "ipc", fake_ipc)
    monkeypatch.delenv("PKM_TEST_MOCK_LLM", raising=False)
    monkeypatch.setattr("pkm.tools.get_pkm_tools", lambda: [])
    monkeypatch.setattr("pkm.models.resolve_auto_models", lambda: [])

    await worker._run_agent_task_impl(
        task_id="models-1",
        session_prefix="pkm-test",
        user_content="question",
        system_prompt="system",
        vault_dir=str(tmp_path),
        model="auto",
    )

    assert fake_ipc.messages[-1] == {
        "type": "error",
        "id": "models-1",
        "message": "No API keys found for any supported models.",
    }


@pytest.mark.anyio
async def test_workflow_dispatch_unknown_id_sends_worker_error(monkeypatch, tmp_path):
    """Unknown workflow ids are reported over IPC without starting an agent."""
    fake_ipc = _FakeIPC()
    monkeypatch.setattr(worker, "ipc", fake_ipc)
    monkeypatch.setattr("pkm.workflows.load_workflows", lambda vault_path: [])

    await worker._dispatch_workflow(
        task_id="wf-missing",
        workflow_id="missing",
        vault_dir=str(tmp_path),
    )

    assert fake_ipc.messages == [
        {
            "type": "error",
            "id": "wf-missing",
            "message": "Unknown workflow_id: missing",
        }
    ]
    records = read_workflow_history(tmp_path)
    assert len(records) == 1
    assert records[0]["workflow_id"] == "missing"
    assert records[0]["status"] == "failure"
    assert records[0]["phase"] == "load"
    assert records[0]["source"] == "unknown"


@pytest.mark.anyio
async def test_workflow_dispatch_formats_pre_hook_and_propagates_agent_options(
    monkeypatch, tmp_path
):
    """Workflow dispatch builds prompt context and forwards runtime options to agent task."""
    config = SimpleNamespace(
        id="weekly",
        pre_hook="prepare",
        post_hook=None,
        system_prompt_template="Today is {today}; focus={focus}",
    )
    calls: list[dict[str, Any]] = []

    def fake_resolve_hook(name):
        if name == "prepare":
            return lambda _vault, today: {"today": today, "focus": "coverage"}
        return None

    async def fake_run_agent_task(**kwargs: Any):
        calls.append(kwargs)
        return SimpleNamespace(
            status="success",
            response="ok",
            result_summary="ok",
            error=None,
        )

    monkeypatch.setattr("pkm.workflows.load_workflows", lambda vault_path: [config])
    monkeypatch.setattr("pkm.workflows.resolve_hook", fake_resolve_hook)
    monkeypatch.setattr(worker, "_run_agent_task", fake_run_agent_task)

    await worker._dispatch_workflow(
        task_id="wf-1",
        workflow_id="weekly",
        vault_dir=str(tmp_path),
        model="test/model",
        env_keys={"OPENAI_API_KEY": "secret"},
        reasoning_effort="high",
        cwd=str(tmp_path / "project"),
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["task_id"] == "wf-1"
    assert call["session_prefix"] == "pkm-weekly"
    assert call["user_content"] == "Execute the weekly workflow now."
    assert "focus=coverage" in call["system_prompt"]
    assert call["model"] == "test/model"
    assert call["env_keys"] == {"OPENAI_API_KEY": "secret"}
    assert call["reasoning_effort"] == "high"
    assert call["cwd"] == str(tmp_path / "project")


@pytest.mark.anyio
async def test_zettelkasten_workflow_reindexes_before_pre_hook_and_agent(
    monkeypatch, tmp_path
):
    """Zettelkasten maintenance refreshes the graph/index before workflow work starts."""
    config = SimpleNamespace(
        id="zettelkasten_maintenance",
        pre_hook="prepare",
        post_hook=None,
        system_prompt_template="Today is {today}.",
    )
    events: list[str] = []

    def fake_rebuild_index(vault):
        events.append(f"index:{vault.path}")

    def fake_resolve_hook(name):
        if name == "prepare":
            return lambda _vault, today: events.append("pre_hook") or {"today": today}
        return None

    async def fake_run_agent_task(**_kwargs: Any):
        events.append("agent")
        return SimpleNamespace(
            status="success",
            response="ok",
            result_summary="ok",
            error=None,
        )

    monkeypatch.setattr("pkm.workflows.load_workflows", lambda vault_path: [config])
    monkeypatch.setattr("pkm.workflows.resolve_hook", fake_resolve_hook)
    monkeypatch.setattr(worker, "_rebuild_workflow_index", fake_rebuild_index)
    monkeypatch.setattr(worker, "_run_agent_task", fake_run_agent_task)

    await worker._dispatch_workflow(
        task_id="wf-index",
        workflow_id="zettelkasten_maintenance",
        vault_dir=str(tmp_path),
    )

    assert events == [f"index:{tmp_path}", "pre_hook", "agent"]


@pytest.mark.anyio
async def test_zettelkasten_workflow_records_index_failure_without_agent_start(
    monkeypatch, tmp_path
):
    """A failed mandatory zettelkasten reindex stops before pre-hook and agent work."""
    fake_ipc = _FakeIPC()
    monkeypatch.setattr(worker, "ipc", fake_ipc)
    config = SimpleNamespace(
        id="zettelkasten_maintenance",
        pre_hook="prepare",
        post_hook=None,
        system_prompt_template="Run maintenance.",
    )

    def fail_rebuild_index(_vault):
        raise RuntimeError("index failed")

    def fail_resolve_hook(_name):
        raise AssertionError("pre-hook should not run after index failure")

    async def fail_run_agent_task(**_kwargs: Any):
        raise AssertionError("agent should not start after index failure")

    monkeypatch.setattr("pkm.workflows.load_workflows", lambda vault_path: [config])
    monkeypatch.setattr("pkm.workflows.resolve_hook", fail_resolve_hook)
    monkeypatch.setattr(worker, "_rebuild_workflow_index", fail_rebuild_index)
    monkeypatch.setattr(worker, "_run_agent_task", fail_run_agent_task)

    await worker._dispatch_workflow(
        task_id="wf-index-fail",
        workflow_id="zettelkasten_maintenance",
        vault_dir=str(tmp_path),
        source="scheduled",
    )

    records = read_workflow_history(tmp_path)
    assert records[0]["status"] == "failure"
    assert records[0]["phase"] == "index"
    assert records[0]["source"] == "scheduled"
    assert "index failed" in records[0]["error"]
    assert fake_ipc.messages[-1]["type"] == "error"


@pytest.mark.anyio
async def test_workflow_dispatch_records_success_history(monkeypatch, tmp_path):
    """A successful workflow records one completion row from the worker boundary."""
    config = SimpleNamespace(
        id="weekly",
        pre_hook=None,
        post_hook=None,
        system_prompt_template="Run weekly workflow.",
    )

    async def fake_run_agent_task(**_kwargs: Any):
        return SimpleNamespace(
            status="success",
            response="verbose response",
            result_summary="tiny turn summary",
            error=None,
        )

    monkeypatch.setattr("pkm.workflows.load_workflows", lambda vault_path: [config])
    monkeypatch.setattr("pkm.workflows.resolve_hook", lambda _name: None)
    monkeypatch.setattr(worker, "_run_agent_task", fake_run_agent_task)
    monkeypatch.setattr(worker.socket, "gethostname", lambda: "history-host")

    await worker._dispatch_workflow(
        task_id="wf-success",
        workflow_id="weekly",
        vault_dir=str(tmp_path),
        source="manual",
    )

    records = read_workflow_history(tmp_path)
    assert len(records) == 1
    assert records[0]["workflow_id"] == "weekly"
    assert records[0]["task_id"] == "wf-success"
    assert records[0]["hostname"] == "history-host"
    assert records[0]["status"] == "success"
    assert records[0]["source"] == "manual"
    assert records[0]["phase"] == "complete"
    assert records[0]["result_summary"] == "tiny turn summary"


@pytest.mark.anyio
async def test_workflow_dispatch_records_pre_hook_failure(monkeypatch, tmp_path):
    """A failing pre-hook records a workflow history failure without agent start."""
    fake_ipc = _FakeIPC()
    monkeypatch.setattr(worker, "ipc", fake_ipc)
    config = SimpleNamespace(
        id="weekly",
        pre_hook="prepare",
        post_hook=None,
        system_prompt_template="Run weekly workflow.",
    )

    def fake_resolve_hook(name):
        if name == "prepare":
            raise RuntimeError("bad hook import")
        return None

    async def fail_run_agent_task(**_kwargs: Any):
        raise AssertionError("agent should not start")

    monkeypatch.setattr("pkm.workflows.load_workflows", lambda vault_path: [config])
    monkeypatch.setattr("pkm.workflows.resolve_hook", fake_resolve_hook)
    monkeypatch.setattr(worker, "_run_agent_task", fail_run_agent_task)

    await worker._dispatch_workflow(
        task_id="wf-pre",
        workflow_id="weekly",
        vault_dir=str(tmp_path),
        source="scheduled",
    )

    records = read_workflow_history(tmp_path)
    assert records[0]["status"] == "failure"
    assert records[0]["phase"] == "pre_hook"
    assert records[0]["source"] == "scheduled"
    assert "bad hook import" in records[0]["error"]
    assert fake_ipc.messages[-1]["type"] == "error"


@pytest.mark.anyio
async def test_workflow_dispatch_records_agent_failure(monkeypatch, tmp_path):
    """A failing tiny-agent turn records an agent-phase workflow failure."""
    config = SimpleNamespace(
        id="weekly",
        pre_hook=None,
        post_hook=None,
        system_prompt_template="Run weekly workflow.",
    )

    async def fake_run_agent_task(**_kwargs: Any):
        return SimpleNamespace(
            status="failure",
            response="",
            result_summary="",
            error="model failed",
        )

    monkeypatch.setattr("pkm.workflows.load_workflows", lambda vault_path: [config])
    monkeypatch.setattr("pkm.workflows.resolve_hook", lambda _name: None)
    monkeypatch.setattr(worker, "_run_agent_task", fake_run_agent_task)

    await worker._dispatch_workflow(
        task_id="wf-agent",
        workflow_id="weekly",
        vault_dir=str(tmp_path),
    )

    records = read_workflow_history(tmp_path)
    assert records[0]["status"] == "failure"
    assert records[0]["phase"] == "agent"
    assert records[0]["source"] == "unknown"
    assert records[0]["error"] == "model failed"


@pytest.mark.anyio
async def test_workflow_dispatch_records_post_hook_failure(monkeypatch, tmp_path):
    """Post-hook failure after agent success is the final workflow outcome."""
    fake_ipc = _FakeIPC()
    monkeypatch.setattr(worker, "ipc", fake_ipc)
    config = SimpleNamespace(
        id="weekly",
        pre_hook=None,
        post_hook="finish",
        system_prompt_template="Run weekly workflow.",
    )

    def fake_resolve_hook(name):
        if name == "finish":
            return lambda _vault, _result: (_ for _ in ()).throw(
                RuntimeError("post hook failed")
            )
        return None

    async def fake_run_agent_task(**_kwargs: Any):
        return SimpleNamespace(
            status="success",
            response="ok",
            result_summary="agent ok",
            error=None,
        )

    monkeypatch.setattr("pkm.workflows.load_workflows", lambda vault_path: [config])
    monkeypatch.setattr("pkm.workflows.resolve_hook", fake_resolve_hook)
    monkeypatch.setattr(worker, "_run_agent_task", fake_run_agent_task)

    await worker._dispatch_workflow(
        task_id="wf-post",
        workflow_id="weekly",
        vault_dir=str(tmp_path),
    )

    records = read_workflow_history(tmp_path)
    assert records[0]["status"] == "failure"
    assert records[0]["phase"] == "post_hook"
    assert records[0]["result_summary"] == "agent ok"
    assert "post hook failed" in records[0]["error"]
    assert fake_ipc.messages[-1]["type"] == "error"


@pytest.mark.anyio
async def test_handle_task_dispatches_workflow_and_unknown_type(monkeypatch, tmp_path):
    """Task dispatch runs sandbox once, routes workflows, and rejects unknown types."""
    fake_ipc = _FakeIPC()
    monkeypatch.setattr(worker, "ipc", fake_ipc)
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_path))
    sandboxed: list[str] = []
    workflow_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(
        "pkm.sandbox.setup_sandbox", lambda path: sandboxed.append(path)
    )
    monkeypatch.setattr(
        worker,
        "agent_credential_env",
        lambda: {"OPENAI_API_KEY": "saved-openai"},
    )

    async def fake_dispatch_workflow(*args: Any, **kwargs: Any) -> None:
        workflow_calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(worker, "_dispatch_workflow", fake_dispatch_workflow)

    await worker._handle_task_with_current_env(
        {
            "id": "task-wf",
            "task_type": "workflow",
            "workflow_id": "weekly",
            "model": "test/model",
            "env_keys": {"K": "V"},
            "reasoning_effort": "medium",
            "cwd": "cwd",
        }
    )
    await worker._handle_task_with_current_env(
        {
            "id": "task-wf-fallback",
            "task_type": "workflow",
            "workflow_id": "weekly",
        }
    )
    await worker._handle_task_with_current_env(
        {"id": "task-bad", "task_type": "unknown"}
    )

    assert sandboxed == [str(tmp_path), str(tmp_path), str(tmp_path)]
    assert workflow_calls[0]["args"] == (
        "task-wf",
        "weekly",
        str(tmp_path),
        "test/model",
        {"K": "V"},
        "medium",
        "cwd",
        "unknown",
    )
    assert workflow_calls[1]["args"][4] == {"OPENAI_API_KEY": "saved-openai"}
    assert fake_ipc.messages[-1] == {
        "type": "error",
        "id": "task-bad",
        "message": "Unknown task type: unknown",
    }


@pytest.mark.anyio
async def test_main_initializes_sandbox_and_reader_loop(monkeypatch, tmp_path):
    """Worker main changes into the vault, initializes sandbox, then reads IPC."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_path))
    sandboxed: list[str] = []
    reader_called = False

    monkeypatch.setattr(
        "pkm.sandbox.setup_sandbox", lambda path: sandboxed.append(path)
    )

    async def fake_reader_loop() -> None:
        nonlocal reader_called
        reader_called = True

    monkeypatch.setattr(worker.ipc, "reader_loop", fake_reader_loop)

    old_cwd = os.getcwd()
    try:
        await worker.main()
    finally:
        os.chdir(old_cwd)

    assert sandboxed == [str(tmp_path)]
    assert reader_called is True
    assert os.getcwd() == old_cwd


@pytest.mark.anyio
async def test_main_applies_trusted_native_sandbox_profile(monkeypatch, tmp_path):
    """Worker startup honors the sandbox profile used by workflow graph tools."""
    from pkm import sandbox

    old_state = dict(sandbox._state)
    sandbox._state.update({"vault_path": None, "installed": False})
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_path))
    monkeypatch.setenv("PKM_WORKER_SANDBOX_PROFILE", "trusted-native")
    hooks = []
    monkeypatch.setattr(sandbox.sys, "addaudithook", lambda hook: hooks.append(hook))
    monkeypatch.setattr(sandbox, "drop_privileges", lambda: None)

    async def fake_reader_loop() -> None:
        return None

    monkeypatch.setattr(worker.ipc, "reader_loop", fake_reader_loop)

    old_cwd = os.getcwd()
    try:
        await worker.main()
    finally:
        os.chdir(old_cwd)
        sandbox._state.clear()
        sandbox._state.update(old_state)

    assert hooks
    hook = hooks[0]
    hook("ctypes.dlopen", ())
    hook("ctypes.dlsym", ())
    with pytest.raises(sandbox.SandboxViolation, match="Command execution blocked"):
        hook("subprocess.Popen", ())
    with pytest.raises(sandbox.SandboxViolation, match="Write access denied"):
        hook("open", (tmp_path.parent / "outside.md", "w"))


@pytest.mark.anyio
async def test_main_exits_when_sandbox_initialization_fails(monkeypatch, tmp_path):
    """Startup sandbox failures stop the worker process before reading IPC."""
    monkeypatch.setenv("PKM_VAULT_DIR", str(tmp_path))

    def fail_sandbox(_path: str) -> None:
        raise RuntimeError("sandbox denied")

    async def fail_reader_loop() -> None:
        raise AssertionError("reader loop should not start")

    monkeypatch.setattr("pkm.sandbox.setup_sandbox", fail_sandbox)
    monkeypatch.setattr(worker.ipc, "reader_loop", fail_reader_loop)

    old_cwd = os.getcwd()
    try:
        with pytest.raises(SystemExit) as exc_info:
            await worker.main()
    finally:
        os.chdir(old_cwd)

    assert exc_info.value.code == 1
