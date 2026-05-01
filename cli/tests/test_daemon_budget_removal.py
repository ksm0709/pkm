"""Regression tests for daemon budget code removal (commit a77b1a1 cleanup).

These tests guard against re-introduction of:
1. self.budget references on LLMWorkerProxy without proper attribute init
2. TokenBudget / BudgetExhausted classes (dead since worker.py refactor)
3. AttributeError in process_background_tasks blocking task dequeue
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


def test_llm_worker_proxy_has_no_budget_attribute():
    """Guard: budget attribute was removed in commit a77b1a1.
    Fails if accidentally re-added without proper cleanup of dead code paths.
    """
    from pkm.daemon import LLMWorkerProxy

    proxy = LLMWorkerProxy()
    assert not hasattr(proxy, "budget"), (
        "LLMWorkerProxy.budget was re-introduced without removing dead "
        "self.budget references — see commit a77b1a1."
    )


def test_process_background_tasks_dequeues_task_without_attributeerror(monkeypatch):
    """Integration test: process_background_tasks must process queued tasks
    without AttributeError on worker_proxy.budget (regression for line 591 bug).

    Uses spec=LLMWorkerProxy so undefined attribute access (e.g. .budget)
    raises AttributeError instead of being auto-mocked. This makes the test
    actually catch re-introduction of `worker_proxy.budget.check_and_consume()`.
    """
    from pkm import daemon
    from pkm.daemon import LLMWorkerProxy

    sample_task = {"id": "test-1", "type": "ask"}

    mock_queue = MagicMock()
    mock_queue.peek.return_value = sample_task
    mock_queue.pop.return_value = sample_task

    mock_worker = MagicMock(spec=LLMWorkerProxy)
    mock_worker.send_task = AsyncMock()

    monkeypatch.setattr("pkm.daemon.task_queue", mock_queue)
    monkeypatch.setattr("pkm.daemon.worker_proxy", mock_worker)

    # process_background_tasks is an infinite while-True loop. Use timeout to break out
    # after the first iteration (which enters await asyncio.sleep(5)).
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(
            asyncio.wait_for(
                daemon.process_background_tasks(),
                timeout=1.0,
            )
        )

    # Critical: send_task must have been awaited exactly once with the popped task.
    # If AttributeError on worker_proxy.budget regressed, this assertion fails (no call).
    mock_worker.send_task.assert_awaited_once_with(sample_task)


def test_process_background_tasks_skips_empty_queue(monkeypatch):
    """Empty queue path: peek returns None → no send_task call."""
    from pkm import daemon

    mock_queue = MagicMock()
    mock_queue.peek.return_value = None

    mock_worker = MagicMock()
    mock_worker.send_task = AsyncMock()

    monkeypatch.setattr("pkm.daemon.task_queue", mock_queue)
    monkeypatch.setattr("pkm.daemon.worker_proxy", mock_worker)

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(
            asyncio.wait_for(
                daemon.process_background_tasks(),
                timeout=1.0,
            )
        )

    mock_worker.send_task.assert_not_awaited()


def test_token_budget_classes_removed():
    """Guard: TokenBudget and BudgetExhausted were removed as dead code in
    the cleanup that completed commit a77b1a1's abandoned refactor.
    """
    from pkm import daemon

    assert not hasattr(daemon, "TokenBudget"), (
        "TokenBudget class re-introduced — worker.py does not emit token_usage "
        "messages so this would be dead code again."
    )
    assert not hasattr(daemon, "BudgetExhausted"), (
        "BudgetExhausted exception re-introduced — only used by removed budget paths."
    )
