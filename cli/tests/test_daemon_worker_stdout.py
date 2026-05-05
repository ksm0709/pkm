"""Tests for daemon worker stdout IPC parsing."""

from __future__ import annotations

import logging

from pkm.daemon import LLMWorkerProxy, _decode_worker_stdout_line, _idle_timeout_disabled


def test_decode_worker_stdout_line_ignores_non_json_noise(caplog) -> None:
    """Third-party stdout logs must not be treated as daemon IPC failures."""
    caplog.set_level(logging.DEBUG, logger="pkm.daemon")

    assert _decode_worker_stdout_line(b"LiteLLM completion() model=gemini\n") is None
    assert "Ignoring non-JSON worker stdout" in caplog.text


def test_decode_worker_stdout_line_accepts_json_message() -> None:
    assert _decode_worker_stdout_line(b'{"type":"result","id":"t1"}\n') == {
        "type": "result",
        "id": "t1",
    }


def test_worker_proxy_has_budget_for_background_tasks() -> None:
    proxy = LLMWorkerProxy()

    proxy.budget.check_and_consume(0)


def test_keepalive_env_disables_idle_timeout(monkeypatch) -> None:
    monkeypatch.setenv("PKM_DAEMON_KEEPALIVE", "1")

    assert _idle_timeout_disabled() is True


def test_idle_timeout_enabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("PKM_DAEMON_KEEPALIVE", raising=False)

    assert _idle_timeout_disabled() is False
