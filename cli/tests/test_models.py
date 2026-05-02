import asyncio
import sys
from types import ModuleType


def test_sync_task_api_keys_removes_stale_daemon_provider_keys(monkeypatch):
    from pkm.worker import sync_task_api_keys

    monkeypatch.setenv("GEMINI_API_KEY", "stale-gemini")
    monkeypatch.setenv("OPENAI_API_KEY", "old-openai")
    monkeypatch.setenv("PKM_TEST_MOCK_LLM", "1")

    sync_task_api_keys({"OPENAI_API_KEY": "fresh-openai"})

    import os

    assert "GEMINI_API_KEY" not in os.environ
    assert os.environ["OPENAI_API_KEY"] == "fresh-openai"
    assert os.environ["PKM_TEST_MOCK_LLM"] == "1"


def test_sync_task_api_keys_treats_blank_request_keys_as_absent(monkeypatch):
    from pkm.worker import sync_task_api_keys

    monkeypatch.setenv("GEMINI_API_KEY", "stale-gemini")
    monkeypatch.setenv("OPENAI_API_KEY", "old-openai")

    sync_task_api_keys({"GEMINI_API_KEY": "", "OPENAI_API_KEY": "fresh-openai"})

    import os

    assert "GEMINI_API_KEY" not in os.environ
    assert os.environ["OPENAI_API_KEY"] == "fresh-openai"


def test_sync_task_api_keys_keeps_daemon_env_when_task_has_no_env_keys(monkeypatch):
    from pkm.worker import sync_task_api_keys

    monkeypatch.setenv("GEMINI_API_KEY", "daemon-gemini")

    sync_task_api_keys(None)

    import os

    assert os.environ["GEMINI_API_KEY"] == "daemon-gemini"


def test_collect_api_keys_omits_blank_values(monkeypatch):
    from pkm.models import collect_api_keys

    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "openai")

    assert collect_api_keys() == {"OPENAI_API_KEY": "openai"}


def test_resolve_auto_models_treats_blank_provider_keys_as_missing(monkeypatch):
    from pkm.models import resolve_auto_models

    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "openai")

    fake_litellm = ModuleType("litellm")

    def validate_environment(model_id):
        if model_id.startswith("gemini/"):
            has_keys = bool(__import__("os").environ.get("GEMINI_API_KEY"))
        elif model_id.startswith("gpt-"):
            has_keys = bool(__import__("os").environ.get("OPENAI_API_KEY"))
        else:
            has_keys = False
        return {"keys_in_environment": has_keys, "missing_keys": []}

    fake_litellm.validate_environment = validate_environment
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    assert resolve_auto_models() == ["gpt-5.4-mini", "gpt-4o-mini"]


def test_resolve_auto_models_includes_openai_when_openai_key_is_available(
    monkeypatch,
):
    from pkm.models import resolve_auto_models

    fake_litellm = ModuleType("litellm")

    def validate_environment(model_id):
        has_keys = model_id.startswith("gpt-")
        return {
            "keys_in_environment": has_keys,
            "missing_keys": [] if has_keys else ["MISSING_API_KEY"],
        }

    fake_litellm.validate_environment = validate_environment
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    assert resolve_auto_models() == ["gpt-5.4-mini", "gpt-4o-mini"]


def test_resolve_model_candidates_prepends_valid_configured_model(monkeypatch):
    from pkm.models import resolve_model_candidates

    monkeypatch.setattr(
        "pkm.models.resolve_auto_models",
        lambda: ["gpt-5.4-mini", "gpt-4o-mini"],
    )
    monkeypatch.setattr("pkm.models._is_valid", lambda model_id: True)

    assert resolve_model_candidates("gemini/gemini-3-flash-preview") == [
        "gemini/gemini-3-flash-preview",
        "gpt-5.4-mini",
        "gpt-4o-mini",
    ]


def test_resolve_model_candidates_skips_configured_model_without_keys(monkeypatch):
    from pkm.models import resolve_model_candidates

    monkeypatch.setattr(
        "pkm.models.resolve_auto_models",
        lambda: ["gpt-5.4-mini", "gpt-4o-mini"],
    )
    monkeypatch.setattr("pkm.models._is_valid", lambda model_id: False)

    assert resolve_model_candidates("gemini/gemini-3-flash-preview") == [
        "gpt-5.4-mini",
        "gpt-4o-mini",
    ]


def test_auto_agent_task_falls_back_to_openai_candidate(monkeypatch):
    from pkm import worker

    monkeypatch.delenv("PKM_TEST_MOCK_LLM", raising=False)
    monkeypatch.setattr(
        "pkm.models.resolve_auto_models",
        lambda: ["gemini/gemini-3-flash-preview", "gpt-4o-mini"],
    )

    models_tried = []

    class FakeAgent:
        def __init__(self, *args, model, **kwargs):
            self.model = model
            models_tried.append(model)

        async def run(self, user_content):
            if self.model.startswith("gemini/"):
                yield {"type": "error", "content": "gemini failed"}
            else:
                yield {"type": "content", "content": f"{self.model}: {user_content}"}

    tiny_agent_package = ModuleType("tiny_agent")
    tiny_agent_agent = ModuleType("tiny_agent.agent")
    tiny_agent_agent.Agent = FakeAgent
    monkeypatch.setitem(sys.modules, "tiny_agent", tiny_agent_package)
    monkeypatch.setitem(sys.modules, "tiny_agent.agent", tiny_agent_agent)

    fake_tools = ModuleType("pkm.tools")
    fake_tools.get_pkm_tools = lambda: []
    monkeypatch.setitem(sys.modules, "pkm.tools", fake_tools)

    messages = []

    class FakeIPC:
        def __init__(self):
            self._abort_event = None

        @property
        def abort_event(self):
            if self._abort_event is None:
                self._abort_event = asyncio.Event()
            return self._abort_event

        async def send_message(self, msg):
            messages.append(msg)

    async def run_task():
        monkeypatch.setattr(worker, "ipc", FakeIPC())
        await worker._run_agent_task(
            task_id="task-1",
            session_prefix="test",
            user_content="hello",
            system_prompt="system",
            vault_dir="/tmp/vault",
            model="auto",
        )

    asyncio.run(run_task())

    assert models_tried == ["gemini/gemini-3-flash-preview", "gpt-4o-mini"]
    assert messages[-1] == {
        "type": "result",
        "id": "task-1",
        "status": "success",
        "data": {"response": "gpt-4o-mini: hello"},
    }


def test_configured_agent_task_falls_back_to_openai_candidate(monkeypatch):
    from pkm import worker

    monkeypatch.delenv("PKM_TEST_MOCK_LLM", raising=False)

    models_tried = []

    class FakeAgent:
        def __init__(self, *args, model, **kwargs):
            self.model = model
            models_tried.append(model)

        async def run(self, user_content):
            if self.model.startswith("gemini/"):
                yield {"type": "error", "content": "gemini failed"}
            else:
                yield {"type": "content", "content": f"{self.model}: {user_content}"}

    tiny_agent_package = ModuleType("tiny_agent")
    tiny_agent_agent = ModuleType("tiny_agent.agent")
    tiny_agent_agent.Agent = FakeAgent
    monkeypatch.setitem(sys.modules, "tiny_agent", tiny_agent_package)
    monkeypatch.setitem(sys.modules, "tiny_agent.agent", tiny_agent_agent)

    fake_tools = ModuleType("pkm.tools")
    fake_tools.get_pkm_tools = lambda: []
    monkeypatch.setitem(sys.modules, "pkm.tools", fake_tools)

    messages = []

    class FakeIPC:
        def __init__(self):
            self._abort_event = None

        @property
        def abort_event(self):
            if self._abort_event is None:
                self._abort_event = asyncio.Event()
            return self._abort_event

        async def send_message(self, msg):
            messages.append(msg)

    async def run_task():
        monkeypatch.setattr(worker, "ipc", FakeIPC())
        await worker._run_agent_task(
            task_id="task-1",
            session_prefix="test",
            user_content="hello",
            system_prompt="system",
            vault_dir="/tmp/vault",
            model="gemini/gemini-3-flash-preview",
            model_candidates=["gemini/gemini-3-flash-preview", "gpt-4o-mini"],
        )

    asyncio.run(run_task())

    assert models_tried == ["gemini/gemini-3-flash-preview", "gpt-4o-mini"]
    assert messages[-1] == {
        "type": "result",
        "id": "task-1",
        "status": "success",
        "data": {"response": "gpt-4o-mini: hello"},
    }
