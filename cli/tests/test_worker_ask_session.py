from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pkm import worker


class _FakeIPC:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self._abort_event = None

    @property
    def abort_event(self):
        import asyncio

        if self._abort_event is None:
            self._abort_event = asyncio.Event()
        return self._abort_event

    async def send_message(self, msg: dict[str, Any]) -> None:
        self.messages.append(msg)


@pytest.mark.anyio
async def test_handle_ask_reuses_tiny_agent_for_same_web_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A stable web ask session id must map to one tiny-agent conversation window."""

    fake_ipc = _FakeIPC()
    monkeypatch.setattr(worker, "ipc", fake_ipc)
    monkeypatch.delenv("PKM_TEST_MOCK_LLM", raising=False)
    monkeypatch.setattr(worker, "_ASK_AGENT_CACHE", {})
    monkeypatch.setattr("pkm.tools.get_pkm_tools", lambda: [])

    instances: list[FakeAgent] = []

    class FakeAgent:
        def __init__(self, session_id: str, **kwargs: Any) -> None:
            self.session_id = session_id
            self.kwargs = kwargs
            self.calls: list[str] = []
            self.tasks: list[dict[str, str]] = []
            self.task_snapshots: list[list[dict[str, str]]] = []
            self.hooks = kwargs.get("hooks", {})
            instances.append(self)

        async def run(self, user_content: str):
            self.task_snapshots.append(list(self.tasks))
            self.calls.append(user_content)
            self.tasks = [{"status": "pending", "title": "stale task"}]
            yield {"type": "content", "content": f"call-{len(self.calls)}"}

    import tiny_agent.agent

    monkeypatch.setattr(tiny_agent.agent, "Agent", FakeAgent)

    await worker.handle_ask(
        task_id="t1",
        query="first question",
        context="",
        vault_dir=str(tmp_path),
        model="test/model",
        ask_session_id="web-alpha-session",
    )
    await worker.handle_ask(
        task_id="t2",
        query="second question",
        context="",
        vault_dir=str(tmp_path),
        model="test/model",
        ask_session_id="web-alpha-session",
    )

    assert len(instances) == 1
    assert instances[0].session_id == "pkm-ask-web-alpha-session"
    assert instances[0].calls == ["first question", "second question"]
    assert instances[0].task_snapshots == [[], []]

    results = [msg for msg in fake_ipc.messages if msg["type"] == "result"]
    assert [msg["data"]["response"] for msg in results] == ["call-1", "call-2"]


@pytest.mark.anyio
async def test_handle_ask_separates_new_web_sessions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The frontend /new flow sends a new id, which must start a fresh agent."""

    monkeypatch.setattr(worker, "ipc", _FakeIPC())
    monkeypatch.delenv("PKM_TEST_MOCK_LLM", raising=False)
    monkeypatch.setattr(worker, "_ASK_AGENT_CACHE", {})
    monkeypatch.setattr("pkm.tools.get_pkm_tools", lambda: [])

    created_session_ids: list[str] = []

    class FakeAgent:
        def __init__(self, session_id: str, **kwargs: Any) -> None:
            self.hooks = kwargs.get("hooks", {})
            created_session_ids.append(session_id)

        async def run(self, user_content: str):
            yield {"type": "content", "content": user_content}

    import tiny_agent.agent

    monkeypatch.setattr(tiny_agent.agent, "Agent", FakeAgent)

    await worker.handle_ask(
        task_id="t1",
        query="old session",
        context="",
        vault_dir=str(tmp_path),
        model="test/model",
        ask_session_id="web-old",
    )
    await worker.handle_ask(
        task_id="t2",
        query="new session",
        context="",
        vault_dir=str(tmp_path),
        model="test/model",
        ask_session_id="web-new",
    )

    assert created_session_ids == ["pkm-ask-web-old", "pkm-ask-web-new"]


@pytest.mark.anyio
async def test_workflow_dispatch_runs_zettelkasten_repair_post_hook(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The zettelkasten workflow must repair malformed notes after the agent turn."""

    vault_dir = tmp_path / "vault"
    notes_dir = vault_dir / "notes"
    notes_dir.mkdir(parents=True)
    (vault_dir / "daily").mkdir()
    (vault_dir / "tags").mkdir()
    malformed = notes_dir / "logger.md"
    malformed.write_text(
        "---\n"
        "id: logger\n"
        "tags: pkm-webapp\n"
        "---\n\n"
        "---\n"
        "aliases: [pkm-webapp-logger]\n"
        "tags: [logging]\n"
        "---\n\n"
        "# Logger\n",
        encoding="utf-8",
    )

    async def fake_run_agent_task(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(worker, "_run_agent_task", fake_run_agent_task)

    await worker._dispatch_workflow(
        task_id="wf-1",
        workflow_id="zettelkasten_maintenance",
        vault_dir=str(vault_dir),
    )

    repaired = malformed.read_text(encoding="utf-8")
    assert repaired.count("---") == 2
    assert "aliases:\n- pkm-webapp-logger" in repaired
    assert "# Logger" in repaired
