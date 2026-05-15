from __future__ import annotations

import json
import socket
import types
from types import SimpleNamespace

from click.testing import CliRunner

from pkm.commands.ask import ask_cmd
from pkm.config import VaultConfig


class FakeSocketFile:
    def __init__(self, lines: list[str] | None = None, error: Exception | None = None):
        self._lines = list(lines or [])
        self._error = error

    def readline(self) -> str:
        if self._error:
            raise self._error
        if not self._lines:
            return ""
        return self._lines.pop(0)


class FakeSocket:
    def __init__(
        self,
        lines: list[str] | None = None,
        connect_error: Exception | None = None,
        readline_error: Exception | None = None,
    ):
        self.lines = lines or []
        self.connect_error = connect_error
        self.readline_error = readline_error
        self.sent_payloads: list[dict] = []
        self.closed = False
        self.timeout = None
        self.connected_to = None

    def settimeout(self, timeout: int) -> None:
        self.timeout = timeout

    def connect(self, path: str) -> None:
        if self.connect_error:
            raise self.connect_error
        self.connected_to = path

    def sendall(self, data: bytes) -> None:
        self.sent_payloads.append(json.loads(data.decode("utf-8")))

    def makefile(self, *_args, **_kwargs) -> FakeSocketFile:
        return FakeSocketFile(self.lines, self.readline_error)

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "FakeSocket":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def _json_line(payload: dict) -> str:
    return json.dumps(payload) + "\n"


def _install_litellm(monkeypatch, validate_environment):
    module = types.ModuleType("litellm")
    module.validate_environment = validate_environment
    monkeypatch.setitem(__import__("sys").modules, "litellm", module)
    return module


def _runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


def _invoke_ask(
    tmp_vault: VaultConfig,
    args: list[str],
    monkeypatch,
    fake_socket: FakeSocket | None = None,
    config: dict | None = None,
    popen=None,
):
    monkeypatch.setattr(
        "pkm.config.load_config",
        lambda: (
            config
            if config is not None
            else {"defaults": {"model": "auto", "graph-depth": 0}}
        ),
    )
    monkeypatch.setattr("time.sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "subprocess.Popen",
        popen if popen is not None else lambda *_args, **_kwargs: SimpleNamespace(),
    )
    if fake_socket is not None:
        monkeypatch.setattr("socket.socket", lambda *_args, **_kwargs: fake_socket)
    return _runner().invoke(ask_cmd, args, obj={"vault": tmp_vault})


def test_list_models_renders_provider_table_and_missing_key_status(monkeypatch):
    """--list-models shows connected provider models and API-key readiness."""
    import pkm.models

    monkeypatch.setattr(
        pkm.models,
        "get_connected_model_options",
        lambda env: ["openai/gpt-test", "anthropic/claude-test"],
    )
    fake_litellm = _install_litellm(
        monkeypatch,
        lambda model_id: {
            "keys_in_environment": model_id == "openai/gpt-test",
            "missing_keys": ["KEY"],
        },
    )
    fake_litellm.model_cost = {
        "openai/gpt-test": {
            "litellm_provider": "openai",
            "max_input_tokens": 128000,
        },
        "anthropic/claude-test": {
            "litellm_provider": "anthropic",
            "max_input_tokens": 200000,
        },
    }

    result = _runner().invoke(ask_cmd, ["--list-models"])

    assert result.exit_code == 0
    assert "PKM Connected LLM Models" in result.output
    assert "openai" in result.output
    assert "anthropic" in result.output
    assert "KEY" in result.output


def test_list_models_reports_missing_litellm(monkeypatch):
    """--list-models gives install guidance when litellm cannot be imported."""
    import builtins

    original_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "litellm":
            raise ImportError("No module named litellm")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    result = _runner().invoke(ask_cmd, ["--list-models"])

    assert result.exit_code == 1
    assert "litellm is not installed" in result.output


def test_no_query_prints_configured_model_and_help(monkeypatch):
    """Calling ask without a query explains the active model and exits before daemon IO."""
    monkeypatch.setattr(
        "pkm.config.load_config",
        lambda: {"defaults": {"model": "configured-model"}},
    )

    result = _runner().invoke(ask_cmd, [])

    assert result.exit_code == 1
    assert "Current LLM model" in result.output
    assert "configured-model" in result.output
    assert "Usage:" in result.output


def test_model_validation_missing_api_key_exits_before_daemon(
    monkeypatch, tmp_vault: VaultConfig
):
    """Explicit model preflight blocks daemon startup when required API keys are missing."""
    _install_litellm(
        monkeypatch,
        lambda _model_id: {
            "keys_in_environment": False,
            "missing_keys": ["OPENAI_API_KEY"],
        },
    )
    fake_socket = FakeSocket([_json_line({"response": "should not happen"})])

    result = _invoke_ask(
        tmp_vault,
        ["--model", "openai/gpt-test", "question"],
        monkeypatch,
        fake_socket=fake_socket,
    )

    assert result.exit_code == 1
    assert "API keys for model" in result.output
    assert "OPENAI_API_KEY" in result.output
    assert fake_socket.sent_payloads == []


def test_model_validation_uses_shared_agent_credentials(
    monkeypatch, tmp_vault: VaultConfig
):
    """Explicit model validation should see the same saved credentials as the task."""

    def validate_environment(_model_id):
        if __import__("os").environ.get("OPENAI_API_KEY") == "saved-openai":
            return {"keys_in_environment": True, "missing_keys": []}
        return {"keys_in_environment": False, "missing_keys": ["OPENAI_API_KEY"]}

    _install_litellm(monkeypatch, validate_environment)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "pkm.commands.ask.agent_credential_env",
        lambda: {"OPENAI_API_KEY": "saved-openai"},
    )
    fake_socket = FakeSocket([_json_line({"data": {"response": "Vault answer"}})])

    result = _invoke_ask(
        tmp_vault,
        ["--model", "openai/gpt-test", "question"],
        monkeypatch,
        fake_socket=fake_socket,
    )

    assert result.exit_code == 0
    assert fake_socket.sent_payloads[0]["env_keys"] == {
        "OPENAI_API_KEY": "saved-openai"
    }
    assert __import__("os").environ.get("OPENAI_API_KEY") is None


def test_ask_sends_daemon_payload_with_config_env_and_reasoning(
    monkeypatch, tmp_vault: VaultConfig
):
    """Happy path sends the full daemon request payload and renders nested response data."""
    _install_litellm(
        monkeypatch,
        lambda _model_id: {"keys_in_environment": True, "missing_keys": []},
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("TEST_API_KEY", "secret")
    fake_socket = FakeSocket([_json_line({"data": {"response": "Vault answer"}})])

    result = _invoke_ask(
        tmp_vault,
        ["--model", "model-x", "--reasoning-effort", "high", "what", "changed"],
        monkeypatch,
        fake_socket=fake_socket,
        config={"defaults": {"graph-depth": 2}},
    )

    assert result.exit_code == 0
    assert "Vault answer" in result.output
    payload = fake_socket.sent_payloads[0]
    assert payload["action"] == "ask"
    assert payload["query"] == "what changed"
    assert payload["vault_name"] == tmp_vault.name
    assert payload["model"] == "model-x"
    assert payload["reasoning_effort"] == "high"
    assert payload["graph_depth"] == 2
    assert payload["env_keys"].get("TEST_API_KEY") == "secret"
    assert all(key.endswith("_API_KEY") for key in payload["env_keys"])
    assert payload["cwd"]


def test_ask_accepts_top_level_response_and_status_success(
    monkeypatch, tmp_vault: VaultConfig
):
    """Daemon response variants complete without treating them as protocol errors."""
    top_level = FakeSocket([_json_line({"response": "Top level answer"})])
    result = _invoke_ask(
        tmp_vault,
        ["question"],
        monkeypatch,
        fake_socket=top_level,
    )
    assert result.exit_code == 0
    assert "Top level answer" in result.output

    success = FakeSocket([_json_line({"status": "success"})])
    result = _invoke_ask(
        tmp_vault,
        ["question"],
        monkeypatch,
        fake_socket=success,
    )
    assert result.exit_code == 0


def test_ask_stream_renders_tool_task_and_reasoning_events(
    monkeypatch, tmp_vault: VaultConfig
):
    """Streaming output shows durable event names while hiding internal tools."""
    long_arg = "x" * 80
    fake_socket = FakeSocket(
        [
            _json_line(
                {
                    "type": "stream",
                    "chunk": {"type": "reasoning", "content": "checking context"},
                }
            ),
            _json_line(
                {
                    "type": "stream",
                    "chunk": {
                        "type": "tool_detail",
                        "name": "turn_start",
                        "arguments": {"hidden": "yes"},
                    },
                }
            ),
            _json_line(
                {
                    "type": "stream",
                    "chunk": {
                        "type": "tool_detail",
                        "name": "manage_tasks",
                        "arguments": {
                            "tasks": [
                                {"title": "Inspect coverage", "status": "done"},
                                {"title": "Add ask tests", "status": "in_progress"},
                            ]
                        },
                    },
                }
            ),
            _json_line(
                {
                    "type": "stream",
                    "chunk": {
                        "type": "tool_detail",
                        "name": "read_note",
                        "arguments": {"note_id": "coverage-plan", "body": long_arg},
                    },
                }
            ),
            _json_line(
                {
                    "type": "stream",
                    "chunk": {
                        "type": "tool_detail",
                        "name": "custom_tool",
                        "arguments": "y" * 120,
                    },
                }
            ),
            _json_line({"response": "stream complete"}),
        ]
    )

    result = _invoke_ask(
        tmp_vault,
        ["stream", "question"],
        monkeypatch,
        fake_socket=fake_socket,
    )

    assert result.exit_code == 0
    assert "Inspect coverage" in result.output
    assert "Add ask tests" in result.output
    assert "read_note" in result.output
    assert "coverage-plan" in result.output
    assert "custom_tool" in result.output
    assert "stream complete" in result.output
    assert "turn_start" not in result.output
    assert "hidden" not in result.output


def test_patch_note_is_highlighted_as_pkm_tool() -> None:
    """ask command treats patch_note as a first-class PKM tool in streams."""
    from pkm.commands.ask import _PKM_TOOLS

    assert "patch_note" in _PKM_TOOLS


def test_ask_reports_daemon_connection_startup_and_protocol_failures(
    monkeypatch, tmp_vault: VaultConfig
):
    """Unhappy daemon paths produce actionable CLI errors."""
    failing_socket = FakeSocket(connect_error=ConnectionRefusedError())
    result = _invoke_ask(
        tmp_vault,
        ["question"],
        monkeypatch,
        fake_socket=failing_socket,
    )
    assert result.exit_code == 1
    assert "Daemon failed to start or connection refused" in result.output

    start_error = FakeSocket(connect_error=FileNotFoundError())
    result = _invoke_ask(
        tmp_vault,
        ["question"],
        monkeypatch,
        fake_socket=start_error,
        popen=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("blocked")),
    )
    assert result.exit_code == 1
    assert "Failed to start daemon" in result.output

    empty = FakeSocket([])
    result = _invoke_ask(tmp_vault, ["question"], monkeypatch, fake_socket=empty)
    assert result.exit_code == 1
    assert "No response from daemon" in result.output

    daemon_error = FakeSocket([_json_line({"type": "error", "message": "bad query"})])
    result = _invoke_ask(tmp_vault, ["question"], monkeypatch, fake_socket=daemon_error)
    assert result.exit_code == 1
    assert "bad query" in result.output

    invalid = FakeSocket([_json_line({"unexpected": True})])
    result = _invoke_ask(tmp_vault, ["question"], monkeypatch, fake_socket=invalid)
    assert result.exit_code == 1
    assert "Invalid response format" in result.output

    timeout = FakeSocket(readline_error=socket.timeout())
    result = _invoke_ask(tmp_vault, ["question"], monkeypatch, fake_socket=timeout)
    assert result.exit_code == 1
    assert "Request timed out" in result.output
