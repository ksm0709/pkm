"""Phase B RED contracts for retiring embedded LLM runtime infrastructure."""

from __future__ import annotations

import asyncio
import builtins
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap
from types import CodeType, ModuleType, SimpleNamespace
from unittest.mock import MagicMock

from click.testing import CliRunner
import pytest

from pkm.config import VaultConfig


CLI_DIR = Path(__file__).resolve().parents[1]
RETIRED_RUNTIME_MODULES = (
    "pkm.worker",
    "pkm.sandbox",
    "pkm.models",
    "pkm.credential_store",
    "pkm.workflows",
    "pkm.tools.daily",
    "pkm.tools.maintenance",
    "pkm.tools.tags",
    "pkm.tools.consolidate",
    "pkm.tools.log",
    "pkm.commands.ask",
    "pkm.commands.workflow",
    "pkm.web.routes.ask",
    "pkm.web.routes.workflows",
)
RETIRED_DAEMON_SYMBOLS = (
    "TaskQueue",
    "LLMWorkerProxy",
    "worker_proxy",
    "task_queue",
    "process_background_tasks",
    "workflow_checker",
    "_on_shutdown",
)


def _import_daemon_in_test_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """Import the daemon without opening its configured log under the real home."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return importlib.import_module("pkm.daemon")


def _nested_string_constants(function) -> set[str]:
    """Collect exact string constants from a function and its nested code objects."""
    found: set[str] = set()

    def visit(code: CodeType) -> None:
        for constant in code.co_consts:
            if isinstance(constant, str):
                found.add(constant)
            elif isinstance(constant, CodeType):
                visit(constant)

    visit(function.__code__)
    return found


def _dependency_name(requirement: str) -> str:
    """Return a normalized distribution name without importing packaging."""
    raw_name = re.split(r"[\s@<>=!~;\[]", requirement, maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", raw_name).lower()


def test_retired_runtime_module_paths_are_absent_but_note_tasks_remain() -> None:
    present = [
        module_name
        for module_name in RETIRED_RUNTIME_MODULES
        if importlib.util.find_spec(module_name) is not None
    ]

    assert present == [], f"retired runtime modules are still importable: {present}"
    assert importlib.util.find_spec("pkm.tasks") is not None


def test_project_dependencies_keep_search_without_embedded_llm_runtime() -> None:
    tomllib = importlib.import_module(
        "tomllib" if sys.version_info >= (3, 11) else "tomli"
    )

    project = tomllib.loads((CLI_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    main = project["project"]["dependencies"]
    optional = project["project"]["optional-dependencies"]
    main_dependencies = {_dependency_name(requirement) for requirement in main}
    declared = set(main_dependencies)
    declared.update(
        _dependency_name(requirement)
        for requirements in optional.values()
        for requirement in requirements
    )

    assert declared.isdisjoint({"litellm", "tiny-agent-py", "keyring"})
    assert "aiohttp" in main_dependencies
    assert "search" in optional
    search_dependencies = {
        _dependency_name(requirement) for requirement in optional["search"]
    }
    assert {"sentence-transformers", "numpy"}.issubset(search_dependencies)


def test_daemon_exports_only_retained_runtime_symbols(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    daemon = _import_daemon_in_test_home(monkeypatch, tmp_path)

    leaked = [name for name in RETIRED_DAEMON_SYMBOLS if hasattr(daemon, name)]
    assert leaked == [], f"daemon still exports retired runtime symbols: {leaked}"


def test_daemon_socket_dispatch_has_no_ask_or_generic_queue_actions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    daemon = _import_daemon_in_test_home(monkeypatch, tmp_path)

    action_constants = _nested_string_constants(daemon.handle_client)
    assert "ask" not in action_constants
    assert "queue_task" not in action_constants
    assert {"search", "update_index", "RELOAD_INDEX"}.issubset(action_constants)


def test_retained_runtime_imports_do_not_load_llm_dependencies(tmp_path: Path) -> None:
    """A clean runtime can import daemon, MCP, search, and graph with LLM deps blocked."""
    script = textwrap.dedent(
        """
        import importlib
        import importlib.abc
        import sys

        forbidden = {"tiny_agent", "litellm", "keyring"}
        blocked = set()

        class BlockLLMImports(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                root = fullname.partition(".")[0]
                if root in forbidden:
                    blocked.add(root)
                    raise ModuleNotFoundError(
                        f"Phase B smoke intentionally blocked {fullname}", name=fullname
                    )
                return None

        sys.meta_path.insert(0, BlockLLMImports())
        for dependency in sorted(forbidden):
            try:
                importlib.import_module(dependency)
            except ModuleNotFoundError as exc:
                assert "intentionally blocked" in str(exc)

        for module_name in (
            "pkm.daemon",
            "pkm.mcp_server",
            "pkm.commands.search",
            "pkm.commands.graph",
            "pkm.search_engine",
            "pkm.graph",
        ):
            importlib.import_module(module_name)

        assert blocked == forbidden
        retired_loaded = sorted(
            name
            for name in sys.modules
            if name == "pkm.credential_store"
            or name == "pkm.workflows"
            or name.startswith("pkm.workflows.")
        )
        assert retired_loaded == [], retired_loaded
        """
    )
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PYTHONPATH": os.pathsep.join(
            filter(None, (str(CLI_DIR / "src"), os.environ.get("PYTHONPATH", "")))
        ),
    }

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_systemd_unit_keeps_daemon_alive_without_worker_configuration() -> None:
    from pkm.commands.setup import SYSTEMD_UNIT_TEMPLATE

    assert "ExecStart=%h/.local/bin/pkm daemon run" in SYSTEMD_UNIT_TEMPLATE
    assert "Environment=PKM_DAEMON_KEEPALIVE=1" in SYSTEMD_UNIT_TEMPLATE
    assert "Restart=on-failure" in SYSTEMD_UNIT_TEMPLATE
    assert "RestartSec=5" in SYSTEMD_UNIT_TEMPLATE
    assert "worker" not in SYSTEMD_UNIT_TEMPLATE.casefold()
    assert "PKM_WORKER_SANDBOX_PROFILE" not in SYSTEMD_UNIT_TEMPLATE


def test_fresh_post_update_syncs_retained_assets_without_workflows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The fresh-process hook syncs skills, aliases, and unit without workflow imports."""
    from pkm.commands.post_update import post_update_cmd
    import pkm.commands.setup as setup

    calls: list[str] = []
    unit_path = tmp_path / "pkm-web.service"
    workflow_path = tmp_path / "workflow.json"
    home = tmp_path / "home"
    config_dir = home / ".config" / "pkm"
    config_dir.mkdir(parents=True)
    queue_path = config_dir / "task_queue.json"
    queue_path.write_text(
        '[{"payload":"secret-bearing legacy task"}]\n', encoding="utf-8"
    )
    durable_workflow_path = config_dir / "workflow.json"
    durable_workflow = b'{"enabled":false}\n'
    durable_workflow_path.write_bytes(durable_workflow)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(
        setup, "install_skill_files", lambda: calls.append("skills") or True
    )
    monkeypatch.setattr(
        setup, "install_shell_aliases", lambda: calls.append("aliases")
    )
    monkeypatch.setattr(
        setup,
        "sync_existing_web_unit",
        lambda: calls.append("unit") or unit_path,
    )

    fake_workflows = ModuleType("pkm.workflows")
    setattr(
        fake_workflows,
        "sync_installed_workflow_defaults",
        lambda: calls.append("workflow-defaults") or workflow_path,
    )
    monkeypatch.setitem(sys.modules, "pkm.workflows", fake_workflows)
    original_import = builtins.__import__

    def record_workflow_import(name, *args, **kwargs):
        if name == "pkm.workflows" or name.startswith("pkm.workflows."):
            calls.append("workflow-import")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", record_workflow_import)
    result = CliRunner().invoke(post_update_cmd, ["--from-version", "2.96.1"])

    assert result.exit_code == 0, str(result.exception or result.output)
    assert calls == ["skills", "aliases", "unit"]
    assert str(unit_path) in result.output
    assert "workflow" not in result.output.casefold()
    assert not queue_path.exists()
    assert durable_workflow_path.read_bytes() == durable_workflow
    assert "secret-bearing" not in result.output


def test_daemon_cleanup_leaves_daily_and_zettel_signal_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Daemon teardown must not hide consolidation work by mutating vault state."""
    daemon = _import_daemon_in_test_home(monkeypatch, tmp_path)
    vault_path = tmp_path / "vault"
    for directory in ("daily", "notes", "tags", ".pkm"):
        (vault_path / directory).mkdir(parents=True)
    vault = VaultConfig(name="vault", path=vault_path)
    daily_path = vault.daily_dir / "2026-04-01.md"
    original_daily = (
        "---\nid: 2026-04-01\ntags:\n  - daily-notes\n---\n"
        "- [09:00] Durable work that still needs explicit distillation\n"
    )
    daily_path.write_text(original_daily, encoding="utf-8")
    signal_path = vault.pkm_dir / "zettel-pending"
    original_signal = b'{"owner":"explicit-user-workflow"}\n'
    signal_path.write_bytes(original_signal)
    monkeypatch.setattr(daemon, "discover_vaults", lambda: {vault.name: vault})

    # Compatibility seam: after retirement there is intentionally no shutdown hook.
    shutdown_hook = getattr(daemon, "_on_shutdown", lambda: None)
    shutdown_hook()

    mutations = []
    if daily_path.read_text(encoding="utf-8") != original_daily:
        mutations.append("daily content/frontmatter")
    if signal_path.read_bytes() != original_signal:
        mutations.append(".pkm/zettel-pending")
    assert mutations == [], f"daemon cleanup mutated: {mutations}"


class _Reader:
    def __init__(self, payload: dict):
        self.payload = payload

    async def readline(self) -> bytes:
        return (json.dumps(self.payload) + "\n").encode("utf-8")


class _Writer:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None

    @property
    def payloads(self) -> list[dict]:
        return [json.loads(line) for line in b"".join(self.chunks).splitlines()]


@pytest.mark.anyio
async def test_unix_daemon_retains_search_update_and_reload_contracts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    daemon = _import_daemon_in_test_home(monkeypatch, tmp_path)
    vault_path = tmp_path / "vault"
    for directory in ("daily", "notes", "tags", ".pkm"):
        (vault_path / directory).mkdir(parents=True)
    vault = VaultConfig(name="vault", path=vault_path)

    async def search_runner(**kwargs):
        assert kwargs["query"] == "retained"
        return [], None

    monkeypatch.setattr(daemon, "resolve_search_vault", lambda _name: vault)
    monkeypatch.setattr(daemon, "run_in_process_search", search_runner)
    monkeypatch.setattr(daemon.DaemonState, "graph_ready", False)
    search_writer = _Writer()
    await daemon.handle_client(
        _Reader({"action": "search", "query": "retained"}), search_writer
    )
    assert search_writer.payloads == [{"results": [], "graph_ready": False}]

    update_calls: list[tuple[VaultConfig, str]] = []

    async def update(vault_arg, *, reason):
        update_calls.append((vault_arg, reason))
        return {"status": "indexed"}

    scheduled = []
    monkeypatch.setattr(daemon, "discover_vaults", lambda: {vault.name: vault})
    monkeypatch.setattr(daemon, "_update_index_for_vault", update)
    monkeypatch.setattr(
        daemon.asyncio,
        "create_task",
        lambda coroutine: scheduled.append(coroutine) or SimpleNamespace(cancel=lambda: None),
    )
    update_writer = _Writer()
    await daemon.handle_client(_Reader({"action": "update_index"}), update_writer)
    assert update_writer.payloads == [{"status": "ok"}]
    await scheduled.pop()
    assert update_calls == [(vault, "manual")]

    reload_calls = []

    class InlineLoop:
        def run_in_executor(self, _executor, function, argument):
            reload_calls.append(argument)
            function(argument)
            future = asyncio.Future()
            future.set_result(None)
            return future

    monkeypatch.setattr(daemon, "_reload_vault_caches", lambda value: None)
    monkeypatch.setattr(daemon.asyncio, "get_running_loop", lambda: InlineLoop())
    reload_writer = _Writer()
    await daemon.handle_client(_Reader({"action": "RELOAD_INDEX"}), reload_writer)
    assert reload_writer.payloads == [{"status": "ok"}]
    assert reload_calls == [vault]


def test_mcp_index_remains_synchronous_and_reports_entry_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import pkm.mcp_server as mcp_server
    import pkm.search_engine as search_engine

    vault = VaultConfig(name="vault", path=tmp_path / "vault")
    result = SimpleNamespace(entries=[object(), object(), object()])
    build_index = MagicMock(return_value=result)
    monkeypatch.setattr(mcp_server, "_current_vault", vault)
    monkeypatch.setattr(search_engine, "build_index", build_index)

    response = mcp_server.index()

    assert response == {"status": "indexed", "count": 3}
    build_index.assert_called_once_with(vault)
