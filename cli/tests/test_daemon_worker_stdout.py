"""Tests for daemon worker stdout IPC parsing."""

from __future__ import annotations

import logging
import time

import pytest

from pkm.daemon import (
    BudgetExhausted,
    LLMWorkerProxy,
    TaskQueue,
    TokenBudget,
    _decode_worker_stdout_line,
    _idle_timeout_disabled,
    redact,
)


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


def test_decode_worker_stdout_line_ignores_non_object_json(caplog) -> None:
    """A JSON array on stdout is still not a valid daemon IPC envelope."""
    caplog.set_level(logging.DEBUG, logger="pkm.daemon")

    assert _decode_worker_stdout_line(b'["result", "t1"]\n') is None
    assert "Ignoring non-object worker stdout JSON" in caplog.text


def test_redact_removes_nested_secret_material_without_destroying_shape() -> None:
    """Logs should preserve enough structure for debugging while hiding keys."""
    payload = {
        "api_key": "sk-secret",
        "nested": [
            {"token": "bearer-secret", "value": 3},
            {"name": "public"},
        ],
    }

    assert redact(payload) == {
        "api_key": "<REDACTED>",
        "nested": [
            {"token": "<REDACTED>", "value": 3},
            {"name": "public"},
        ],
    }


def test_token_budget_tracks_consumption_and_blocks_overages() -> None:
    """Background LLM tasks must stop before crossing the configured budget."""
    budget = TokenBudget(max_tokens=10, window_seconds=60, window_start=time.time())

    budget.check_and_consume(4)
    budget.check_and_consume(6)

    assert budget.used_tokens == 10
    with pytest.raises(BudgetExhausted, match="Used 10/10"):
        budget.check_and_consume(1)


def test_token_budget_resets_after_window_expires() -> None:
    budget = TokenBudget(
        max_tokens=10,
        window_seconds=1,
        used_tokens=9,
        window_start=time.time() - 2,
    )

    budget.check_and_consume(5)

    assert budget.used_tokens == 5


def test_task_queue_persists_fifo_order_across_instances(tmp_path) -> None:
    """Queued background tasks should survive daemon restarts in FIFO order."""
    db_path = tmp_path / "tasks.json"
    queue = TaskQueue(db_path)

    queue.push({"id": "first", "type": "ask"})
    queue.push({"id": "second", "type": "index"})

    reloaded = TaskQueue(db_path)
    assert reloaded.peek() == {"id": "first", "type": "ask"}
    assert reloaded.pop() == {"id": "first", "type": "ask"}
    assert reloaded.pop() == {"id": "second", "type": "index"}
    assert reloaded.pop() is None
    assert TaskQueue(db_path).queue == []


def test_task_queue_recovers_from_corrupt_persistence(tmp_path) -> None:
    db_path = tmp_path / "tasks.json"
    db_path.write_text("{not-json", encoding="utf-8")

    queue = TaskQueue(db_path)

    assert queue.peek() is None
    queue.push({"id": "new"})
    assert TaskQueue(db_path).pop() == {"id": "new"}


def test_worker_proxy_has_budget_for_background_tasks() -> None:
    proxy = LLMWorkerProxy()

    proxy.budget.check_and_consume(0)


def test_keepalive_env_disables_idle_timeout(monkeypatch) -> None:
    monkeypatch.setenv("PKM_DAEMON_KEEPALIVE", "1")

    assert _idle_timeout_disabled() is True


def test_idle_timeout_enabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("PKM_DAEMON_KEEPALIVE", raising=False)

    assert _idle_timeout_disabled() is False
