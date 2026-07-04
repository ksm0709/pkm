"""Daemon idle auto-index behavior."""

from __future__ import annotations

from types import SimpleNamespace
import threading

import pytest

from pkm import daemon as daemon_mod


@pytest.fixture
def daemon_state(monkeypatch):
    class _State:
        last_activity = 0.0
        active_requests = 0
        current_task = None
        graph_ready = True
        auto_index_last_attempt: dict[str, float] = {}
        indexing_vaults: set[str] = set()

    monkeypatch.setattr(daemon_mod, "DaemonState", _State)
    monkeypatch.setenv("PKM_DAEMON_AUTO_INDEX_ENABLED", "true")
    monkeypatch.setenv("PKM_DAEMON_AUTO_INDEX_IDLE_SECONDS", "10")
    monkeypatch.setenv("PKM_DAEMON_AUTO_INDEX_MIN_INTERVAL_SECONDS", "0")
    return _State


@pytest.mark.anyio
async def test_auto_index_runs_for_stale_vault_after_idle(
    tmp_vault, daemon_state, monkeypatch
) -> None:
    calls = []

    async def fake_update_index(vault, *, reason):
        calls.append((vault, reason))
        return {"status": "indexed", "vault": vault.name, "reason": reason}

    monkeypatch.setattr(
        daemon_mod, "discover_vaults", lambda: {tmp_vault.name: tmp_vault}
    )
    monkeypatch.setattr(daemon_mod, "is_index_stale", lambda vault: True)
    monkeypatch.setattr(daemon_mod, "_update_index_for_vault", fake_update_index)

    daemon_state.last_activity = 80.0

    results = await daemon_mod.run_auto_index_once(now=100.0)

    assert calls == [(tmp_vault, "auto-idle")]
    assert results == [{"status": "indexed", "vault": tmp_vault.name, "reason": "auto-idle"}]


@pytest.mark.anyio
async def test_auto_index_skips_when_recent_activity(
    tmp_vault, daemon_state, monkeypatch
) -> None:
    calls = []

    async def fake_update_index(vault, *, reason):
        calls.append(vault)
        return {"status": "indexed"}

    monkeypatch.setattr(
        daemon_mod, "discover_vaults", lambda: {tmp_vault.name: tmp_vault}
    )
    monkeypatch.setattr(daemon_mod, "is_index_stale", lambda vault: True)
    monkeypatch.setattr(daemon_mod, "_update_index_for_vault", fake_update_index)

    daemon_state.last_activity = 95.0

    results = await daemon_mod.run_auto_index_once(now=100.0)

    assert results == []
    assert calls == []


@pytest.mark.anyio
async def test_auto_index_skips_while_request_is_active(
    tmp_vault, daemon_state, monkeypatch
) -> None:
    calls = []

    async def fake_update_index(vault, *, reason):
        calls.append(vault)
        return {"status": "indexed"}

    monkeypatch.setattr(
        daemon_mod, "discover_vaults", lambda: {tmp_vault.name: tmp_vault}
    )
    monkeypatch.setattr(daemon_mod, "is_index_stale", lambda vault: True)
    monkeypatch.setattr(daemon_mod, "_update_index_for_vault", fake_update_index)

    daemon_state.last_activity = 80.0
    daemon_state.active_requests = 1

    results = await daemon_mod.run_auto_index_once(now=100.0)

    assert results == []
    assert calls == []


@pytest.mark.anyio
async def test_auto_index_skips_fresh_vault(tmp_vault, daemon_state, monkeypatch) -> None:
    calls = []

    async def fake_update_index(vault, *, reason):
        calls.append(vault)
        return {"status": "indexed"}

    monkeypatch.setattr(
        daemon_mod, "discover_vaults", lambda: {tmp_vault.name: tmp_vault}
    )
    monkeypatch.setattr(daemon_mod, "is_index_stale", lambda vault: False)
    monkeypatch.setattr(daemon_mod, "_update_index_for_vault", fake_update_index)

    daemon_state.last_activity = 80.0

    results = await daemon_mod.run_auto_index_once(now=100.0)

    assert results == []
    assert calls == []


@pytest.mark.anyio
async def test_auto_index_respects_min_attempt_interval(
    tmp_vault, daemon_state, monkeypatch
) -> None:
    calls = []

    async def fake_update_index(vault, *, reason):
        calls.append(vault)
        return {"status": "indexed"}

    monkeypatch.setenv("PKM_DAEMON_AUTO_INDEX_MIN_INTERVAL_SECONDS", "60")
    monkeypatch.setattr(
        daemon_mod, "discover_vaults", lambda: {tmp_vault.name: tmp_vault}
    )
    monkeypatch.setattr(daemon_mod, "is_index_stale", lambda vault: True)
    monkeypatch.setattr(daemon_mod, "_update_index_for_vault", fake_update_index)

    daemon_state.last_activity = 0.0
    daemon_state.auto_index_last_attempt[str(tmp_vault.path)] = 90.0

    results = await daemon_mod.run_auto_index_once(now=100.0)

    assert results == []
    assert calls == []


@pytest.mark.anyio
async def test_auto_index_does_not_bump_last_activity(
    tmp_vault, daemon_state, monkeypatch
) -> None:
    async def fake_update_index(vault, *, reason):
        return {"status": "indexed"}

    monkeypatch.setattr(
        daemon_mod, "discover_vaults", lambda: {tmp_vault.name: tmp_vault}
    )
    monkeypatch.setattr(daemon_mod, "is_index_stale", lambda vault: True)
    monkeypatch.setattr(daemon_mod, "_update_index_for_vault", fake_update_index)

    daemon_state.last_activity = 80.0

    await daemon_mod.run_auto_index_once(now=100.0)

    assert daemon_state.last_activity == 80.0


@pytest.mark.anyio
async def test_update_index_for_vault_skips_duplicate_queued_vault(
    tmp_vault, daemon_state, monkeypatch
) -> None:
    started = threading.Event()
    release = threading.Event()
    calls = []

    def fake_run_index_update(vault):
        calls.append(vault)
        started.set()
        assert release.wait(2.0)
        return 1

    monkeypatch.setattr(daemon_mod, "_run_index_update", fake_run_index_update)

    first = daemon_mod.asyncio.create_task(
        daemon_mod._update_index_for_vault(tmp_vault, reason="manual")
    )
    loop = daemon_mod.asyncio.get_running_loop()
    await loop.run_in_executor(None, started.wait)

    duplicate = await daemon_mod._update_index_for_vault(tmp_vault, reason="manual")

    release.set()
    first_result = await first

    assert duplicate == {
        "status": "skipped",
        "reason": "already-indexing",
        "vault": tmp_vault.name,
    }
    assert first_result == {
        "status": "indexed",
        "vault": tmp_vault.name,
        "reason": "manual",
        "count": 1,
    }
    assert calls == [tmp_vault]


def test_atomic_index_write_replaces_existing_file(tmp_path) -> None:
    from pkm.search_engine import atomic_write_json

    target = tmp_path / "index.json"
    target.write_text('{"old": true}', encoding="utf-8")

    atomic_write_json(target, {"new": True})

    assert target.read_text(encoding="utf-8") == '{"new": true}'
    assert not list(tmp_path.glob("*.tmp"))
