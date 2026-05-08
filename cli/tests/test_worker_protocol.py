from __future__ import annotations

import asyncio
import io
import json
import sys
from collections import OrderedDict
from typing import Any

import pytest

from pkm import worker


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

    await worker._run_agent_task_impl(
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
