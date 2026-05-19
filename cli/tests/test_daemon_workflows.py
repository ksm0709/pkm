"""Tests for daemon workflow scheduling behavior."""

from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path

import pytest

from pkm.config import VaultConfig
from pkm.workflows.history import append_workflow_history
from pkm.workflows import WorkflowConfig


class RecordingQueue:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def push(self, task: dict) -> None:
        self.items.append(task)


def test_workflow_marker_allows_retry_after_other_host_failure(tmp_path):
    """A failed claim from another host must not block this host's scheduled run."""
    import pkm.daemon as daemon

    vault_path = tmp_path / "vault"
    marker_path = vault_path / ".pkm" / "wf-last-run"
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text(
        json.dumps({"date": "2026-05-19", "host": "b850m"}),
        encoding="utf-8",
    )
    append_workflow_history(
        vault_path,
        {
            "workflow_id": "wf",
            "task_id": "wf_vault_1",
            "hostname": "b850m",
            "time": "2026-05-18T17:07:11.223984Z",
            "status": "failure",
            "source": "scheduled",
            "phase": "index",
            "error": "Command execution blocked: subprocess.Popen",
            "result_summary": "",
        },
    )

    blocks, host = daemon._workflow_marker_blocks_scheduled_run(
        vault_path=vault_path,
        workflow_id="wf",
        marker_path=marker_path,
        current_date=datetime.date(2026, 5, 19),
        hostname="lgubook",
    )

    assert blocks is False
    assert host == "b850m"


def test_workflow_marker_blocks_after_same_day_success(tmp_path):
    """A completed run still prevents duplicate same-day workflow execution."""
    import pkm.daemon as daemon

    vault_path = tmp_path / "vault"
    marker_path = vault_path / ".pkm" / "wf-last-run"
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text(
        json.dumps({"date": "2026-05-19", "host": "b850m"}),
        encoding="utf-8",
    )
    append_workflow_history(
        vault_path,
        {
            "workflow_id": "wf",
            "task_id": "wf_vault_1",
            "hostname": "b850m",
            "time": "2026-05-19T02:30:00+09:00",
            "status": "success",
            "source": "scheduled",
            "phase": "complete",
            "error": None,
            "result_summary": "done",
        },
    )

    blocks, host = daemon._workflow_marker_blocks_scheduled_run(
        vault_path=vault_path,
        workflow_id="wf",
        marker_path=marker_path,
        current_date=datetime.date(2026, 5, 19),
        hostname="lgubook",
    )

    assert blocks is True
    assert host == "b850m"


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


@pytest.mark.anyio
async def test_workflow_checker_marks_scheduled_queue_source(monkeypatch, tmp_path):
    """Scheduled workflow entries carry source metadata and shared credentials."""
    import pkm.daemon as daemon

    vault_path = tmp_path / "vault"
    (vault_path / ".pkm").mkdir(parents=True)
    vault = VaultConfig(name="vault", path=vault_path)

    queue = RecordingQueue()
    monkeypatch.setattr(daemon, "task_queue", queue)
    monkeypatch.setattr(daemon, "discover_vaults", lambda: {"vault": vault})
    monkeypatch.setattr(daemon, "jitter_minutes", lambda _config: 0)
    monkeypatch.setattr(
        daemon,
        "agent_credential_env",
        lambda: {"OPENAI_API_KEY": "saved-openai"},
    )

    class FixedDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 5, 10, 12, 0, tzinfo=tz)

    monkeypatch.setattr(daemon.datetime, "datetime", FixedDatetime)

    sleep_calls = 0

    async def fake_sleep(_seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(daemon.asyncio, "sleep", fake_sleep)

    config = WorkflowConfig(
        id="wf_scheduled",
        schedule_hour=12,
        jitter_type="md5_hostname",
        marker_file="wf-scheduled-last-run",
        system_prompt_template="Run scheduled workflow.",
        enabled=True,
    )
    monkeypatch.setattr(daemon, "load_workflows", lambda vault_path: [config])

    with pytest.raises(asyncio.CancelledError):
        await daemon.workflow_checker(config)

    assert len(queue.items) == 1
    assert queue.items[0]["workflow_source"] == "scheduled"
    assert queue.items[0]["workflow_id"] == "wf_scheduled"
    assert queue.items[0]["env_keys"] == {"OPENAI_API_KEY": "saved-openai"}
