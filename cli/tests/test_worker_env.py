from __future__ import annotations

import asyncio
import os

import pytest

from pkm import worker


@pytest.mark.anyio
async def test_run_agent_task_restores_env_keys_after_mock_task(monkeypatch) -> None:
    monkeypatch.setenv("PKM_TEST_MOCK_LLM", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "original")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    sent: list[dict] = []

    async def fake_send_message(msg: dict) -> None:
        sent.append(msg)
        assert os.environ["OPENAI_API_KEY"] == "temporary"
        assert os.environ["GEMINI_API_KEY"] == "gemini-secret"

    monkeypatch.setattr(worker.ipc, "send_message", fake_send_message)

    await worker._run_agent_task(
        task_id="env-test",
        session_prefix="pkm-test",
        user_content="hello",
        system_prompt="system",
        vault_dir=".",
        env_keys={"OPENAI_API_KEY": "temporary", "GEMINI_API_KEY": "gemini-secret"},
    )

    assert sent[-1]["type"] == "result"
    assert os.environ["OPENAI_API_KEY"] == "original"
    assert "GEMINI_API_KEY" not in os.environ


@pytest.mark.anyio
async def test_env_scopes_serialize_and_restore_concurrent_tasks(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "original")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    observations: list[tuple[str, str | None, str | None]] = []

    async def first_task() -> None:
        observations.append(
            (
                "first-start",
                os.environ.get("OPENAI_API_KEY"),
                os.environ.get("ANTHROPIC_API_KEY"),
            )
        )
        first_entered.set()
        await release_first.wait()
        observations.append(
            (
                "first-end",
                os.environ.get("OPENAI_API_KEY"),
                os.environ.get("ANTHROPIC_API_KEY"),
            )
        )

    async def second_task() -> None:
        await first_entered.wait()
        observations.append(
            (
                "second-before-lock",
                os.environ.get("OPENAI_API_KEY"),
                os.environ.get("ANTHROPIC_API_KEY"),
            )
        )
        await worker._run_with_env(
            {"OPENAI_API_KEY": "second", "ANTHROPIC_API_KEY": "anthropic"},
            lambda: _record_env("second-inside", observations),
        )

    first = asyncio.create_task(
        worker._run_with_env({"OPENAI_API_KEY": "first"}, first_task)
    )
    second = asyncio.create_task(second_task())
    await first_entered.wait()
    await asyncio.sleep(0)
    release_first.set()
    await asyncio.gather(first, second)

    assert observations == [
        ("first-start", "first", None),
        ("second-before-lock", "first", None),
        ("first-end", "first", None),
        ("second-inside", "second", "anthropic"),
    ]
    assert os.environ["OPENAI_API_KEY"] == "original"
    assert "ANTHROPIC_API_KEY" not in os.environ


@pytest.mark.anyio
async def test_handle_task_restores_msg_env(monkeypatch) -> None:
    monkeypatch.setenv("PKM_TEST_MOCK_LLM", "1")
    monkeypatch.setenv("PKM_VAULT_DIR", "original-vault")
    monkeypatch.setattr("pkm.sandbox.setup_sandbox", lambda _vault_dir: None)
    seen_vaults: list[str] = []

    async def fake_handle_ask(*args, **kwargs) -> None:
        seen_vaults.append(os.environ["PKM_VAULT_DIR"])

    monkeypatch.setattr(worker, "handle_ask", fake_handle_ask)

    await worker.handle_task(
        {
            "id": "handle-env-test",
            "task_type": "ask",
            "query": "hello",
            "env": {"PKM_VAULT_DIR": "task-vault"},
        }
    )

    assert seen_vaults == ["task-vault"]
    assert os.environ["PKM_VAULT_DIR"] == "original-vault"


@pytest.mark.anyio
async def test_handle_task_deletes_msg_env_that_was_absent(monkeypatch) -> None:
    monkeypatch.setenv("PKM_TEST_MOCK_LLM", "1")
    monkeypatch.delenv("PKM_VAULT_DIR", raising=False)
    monkeypatch.setattr("pkm.sandbox.setup_sandbox", lambda _vault_dir: None)
    seen_vaults: list[str] = []

    async def fake_handle_ask(*args, **kwargs) -> None:
        seen_vaults.append(os.environ["PKM_VAULT_DIR"])

    monkeypatch.setattr(worker, "handle_ask", fake_handle_ask)

    await worker.handle_task(
        {
            "id": "handle-env-delete-test",
            "task_type": "ask",
            "query": "hello",
            "env": {"PKM_VAULT_DIR": "task-vault"},
        }
    )

    assert seen_vaults == ["task-vault"]
    assert "PKM_VAULT_DIR" not in os.environ


async def _record_env(
    label: str, observations: list[tuple[str, str | None, str | None]]
) -> None:
    observations.append(
        (
            label,
            os.environ.get("OPENAI_API_KEY"),
            os.environ.get("ANTHROPIC_API_KEY"),
        )
    )
