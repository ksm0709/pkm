"""Tests for daemon workflow scheduling behavior."""

from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path

import pytest

from pkm.config import VaultConfig
from pkm.workflows import WorkflowConfig


class RecordingQueue:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def push(self, task: dict) -> None:
        self.items.append(task)


@pytest.mark.anyio
async def test_workflow_checker_skips_when_latest_vault_config_is_disabled(
    monkeypatch, tmp_path
):
    """A running workflow checker must re-read vault config before queueing."""
    import pkm.daemon as daemon

    home = Path.home()
    cfg_dir = home / ".config" / "pkm"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "workflow.json").write_text(
        json.dumps(
            [
                {
                    "id": "wf_dynamic",
                    "schedule_hour": 12,
                    "jitter_type": "md5_hostname",
                    "marker_file": "wf-dynamic-last-run",
                    "system_prompt_template": "Run dynamic workflow.",
                    "enabled": True,
                }
            ]
        ),
        encoding="utf-8",
    )

    vault_path = tmp_path / "vault"
    (vault_path / ".pkm").mkdir(parents=True)
    (vault_path / ".pkm" / "workflow.json").write_text(
        json.dumps([{"id": "wf_dynamic", "enabled": False}]),
        encoding="utf-8",
    )
    vault = VaultConfig(name="vault", path=vault_path)

    queue = RecordingQueue()
    monkeypatch.setattr(daemon, "task_queue", queue)
    monkeypatch.setattr(daemon, "discover_vaults", lambda: {"vault": vault})
    monkeypatch.setattr(daemon, "jitter_minutes", lambda _config: 0)

    class FixedDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 5, 3, 12, 0, tzinfo=tz)

    monkeypatch.setattr(daemon.datetime, "datetime", FixedDatetime)

    sleep_calls = 0

    async def fake_sleep(_seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(daemon.asyncio, "sleep", fake_sleep)

    config = WorkflowConfig(
        id="wf_dynamic",
        schedule_hour=12,
        jitter_type="md5_hostname",
        marker_file="wf-dynamic-last-run",
        system_prompt_template="Run dynamic workflow.",
        enabled=True,
    )

    with pytest.raises(asyncio.CancelledError):
        await daemon.workflow_checker(config)

    assert queue.items == []
    assert not (vault_path / ".pkm" / "wf-dynamic-last-run").exists()
