"""Scenario tests for daemon socket protocol handlers and helper loops."""

from __future__ import annotations

import asyncio
import json
import logging
from types import SimpleNamespace

import pytest

from pkm.config import VaultConfig
from pkm.search_engine import SearchResult


def test_web_startup_announcement_includes_url_and_port(caplog, capsys) -> None:
    """Web startup announces the listening port to both logs and systemd stdout."""
    import pkm.daemon as daemon

    caplog.set_level(logging.INFO, logger="pkm.daemon")

    daemon._announce_web_server_started("127.0.0.1", 7420)

    out = capsys.readouterr().out
    assert "PKM web server listening on http://127.0.0.1:7420" in out
    assert "PKM web server listening on http://127.0.0.1:7420" in caplog.text


def test_web_listen_url_formats_ipv6_hosts() -> None:
    """IPv6 bind addresses need brackets in readable URLs."""
    import pkm.daemon as daemon

    assert daemon._web_listen_url("::1", 7420) == "http://[::1]:7420"


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
async def test_handle_client_index_and_reload_paths(
    tmp_vault: VaultConfig, monkeypatch
) -> None:
    """Index actions return protocol responses without real daemon state."""
    import pkm.daemon as daemon

    monkeypatch.setattr(daemon, "discover_vaults", lambda: {})
    no_vault_writer = FakeWriter()
    await daemon.handle_client(
        FakeReader({"action": "update_index", "vault_name": "missing"}), no_vault_writer
    )
    assert no_vault_writer.json_lines == [{"error": "vault not found"}]

    run_calls: list[tuple[str, object]] = []
    update_calls: list[tuple[VaultConfig, str]] = []
    scheduled_coroutines = []

    class InlineLoop:
        def run_in_executor(self, executor, fn, arg):
            run_calls.append((fn.__name__, arg))
            fn(arg)
            future = asyncio.Future()
            future.set_result(None)
            return future

    async def fake_update_index(vault, *, reason):
        update_calls.append((vault, reason))
        return {"status": "indexed"}

    def fake_create_task(coro):
        scheduled_coroutines.append(coro)
        return SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr(daemon.asyncio, "get_running_loop", lambda: InlineLoop())
    monkeypatch.setattr(daemon.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(daemon, "discover_vaults", lambda: {"vault": tmp_vault})
    monkeypatch.setattr(daemon, "_update_index_for_vault", fake_update_index)
    monkeypatch.setattr(daemon, "_reload_vault_caches", lambda vault: None)

    update_writer = FakeWriter()
    await daemon.handle_client(FakeReader({"action": "update_index"}), update_writer)
    assert update_writer.json_lines == [{"status": "ok"}]
    assert len(scheduled_coroutines) == 1
    await scheduled_coroutines.pop()
    assert update_calls == [(tmp_vault, "manual")]

    reload_writer = FakeWriter()
    await daemon.handle_client(FakeReader({"action": "RELOAD_INDEX"}), reload_writer)
    assert reload_writer.json_lines == [{"status": "ok"}]
    assert run_calls[-1][0] == "<lambda>"


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
    monkeypatch.setattr(daemon, "_activity_now", lambda: 10_000)
    daemon.DaemonState.last_activity = 0

    await daemon.idle_checker(server)

    assert server.closed is True
