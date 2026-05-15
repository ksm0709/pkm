"""Tests for pkm workflow list/run CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import pytest
from pkm.cli import main
from pkm.commands.workflow import workflow_group
from pkm.config import VaultConfig
from pkm.workflows.history import append_workflow_history


def _write_workflow_json(path: Path, entries: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")


def test_workflow_list_shows_bundled_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["workflow", "list"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    ids = [w["id"] for w in payload]
    assert "zettelkasten_maintenance" in ids
    assert "daily_task_summary" not in ids
    by_id = {w["id"]: w for w in payload}
    assert by_id["zettelkasten_maintenance"]["enabled"] is False


def test_workflow_list_shows_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _write_workflow_json(
        tmp_path / ".config" / "pkm" / "workflow.json",
        [
            {
                "id": "my_wf",
                "schedule_hour": 3,
                "jitter_type": "md5_hostname",
                "marker_file": "my-last-run",
                "system_prompt_template": "hello",
                "pre_hook": None,
                "post_hook": None,
            }
        ],
    )
    runner = CliRunner()
    result = runner.invoke(main, ["workflow", "list"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    ids = [w["id"] for w in payload]
    assert "my_wf" in ids
    assert any(w["schedule_hour"] == 3 for w in payload if w["id"] == "my_wf")
    assert any(w["enabled"] is False for w in payload if w["id"] == "my_wf")
    assert "3" in result.output


def test_workflow_list_table_renders_workflow_hooks(tmp_path, monkeypatch):
    """Table output gives operators scan-friendly workflow details and hook names."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("pkm.commands.workflow._console.width", 180)
    _write_workflow_json(
        tmp_path / ".config" / "pkm" / "workflow.json",
        [
            {
                "id": "nightly_review",
                "schedule_hour": 4,
                "jitter_type": "md5_hostname_suffix:review",
                "marker_file": "nightly-review-last-run",
                "system_prompt_template": "review",
                "pre_hook": "pkm.workflows.hooks:build_daily_summary",
                "post_hook": "pkm.workflows.hooks:repair_malformed_notes",
            }
        ],
    )
    runner = CliRunner()

    result = runner.invoke(main, ["workflow", "list", "--format", "table"])

    assert result.exit_code == 0, result.output
    assert "PKM Workflows" in result.output
    assert "nightly_review" in result.output
    assert "4" in result.output
    assert "md5_hostname_suffix:review" in result.output
    assert "nightly-review-last-run" in result.output
    assert "build_daily_summary" in result.output
    assert "repair_malformed_notes" in result.output
    assert not result.output.lstrip().startswith("[")


def test_workflow_list_table_guides_when_no_workflows(monkeypatch):
    """Table output explains how to configure workflows when none are loaded."""
    monkeypatch.setattr(
        "pkm.commands.workflow.load_workflows", lambda vault_path=None: []
    )
    runner = CliRunner()

    result = runner.invoke(main, ["workflow", "list", "--format", "table"])

    assert result.exit_code == 0, result.output
    assert "No workflows configured" in result.output
    assert "~/.config/pkm/workflow.json" in result.output


def test_workflow_run_unknown_id(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["workflow", "run", "daily_task_summary"])
    assert result.exit_code != 0
    assert "Unknown workflow ID" in result.output


def test_workflow_run_queues_task_as_json_array(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    queue_path = tmp_path / ".config" / "pkm" / "task_queue.json"

    runner = CliRunner()
    result = runner.invoke(main, ["workflow", "run", "zettelkasten_maintenance"])
    assert result.exit_code == 0
    assert "Queued workflow" in result.output

    assert queue_path.exists()
    queue = json.loads(queue_path.read_text())
    assert isinstance(queue, list), "task_queue.json must be a raw JSON array"
    assert len(queue) == 1
    assert queue[0]["task_type"] == "workflow"
    assert queue[0]["workflow_id"] == "zettelkasten_maintenance"
    assert queue[0]["workflow_source"] == "manual"


def test_workflow_run_queues_task_with_injected_vault_env(tmp_path, monkeypatch):
    """Direct command queues the vault path and shared agent credentials."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    vault = VaultConfig(name="work", path=tmp_path / "vaults" / "work")
    monkeypatch.setattr("pkm.commands.workflow.time.time", lambda: 42)
    monkeypatch.setattr(
        "pkm.commands.workflow.agent_credential_env",
        lambda: {"OPENAI_API_KEY": "saved-openai"},
    )

    runner = CliRunner()
    result = runner.invoke(
        workflow_group,
        ["run", "zettelkasten_maintenance"],
        obj={"vault": vault},
    )

    assert result.exit_code == 0, result.output
    queue_path = tmp_path / ".config" / "pkm" / "task_queue.json"
    queue = json.loads(queue_path.read_text())
    assert queue == [
        {
            "type": "task",
            "id": "zettelkasten_maintenance_manual_42",
            "task_type": "workflow",
            "workflow_id": "zettelkasten_maintenance",
            "workflow_source": "manual",
            "env_keys": {"OPENAI_API_KEY": "saved-openai"},
            "env": {"PKM_VAULT_DIR": str(vault.path)},
        }
    ]


@pytest.mark.parametrize(
    "bad_queue",
    [
        json.dumps({"bad": True}),
        "{not valid json",
    ],
)
def test_workflow_run_replaces_corrupt_queue_state(
    tmp_path, monkeypatch, bad_queue: str
):
    """Corrupt daemon queue state is replaced with a valid one-item workflow queue."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    queue_path = tmp_path / ".config" / "pkm" / "task_queue.json"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(bad_queue, encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["workflow", "run", "zettelkasten_maintenance"])

    assert result.exit_code == 0, result.output
    queue = json.loads(queue_path.read_text())
    assert isinstance(queue, list)
    assert len(queue) == 1
    assert queue[0]["task_type"] == "workflow"
    assert queue[0]["workflow_id"] == "zettelkasten_maintenance"
    assert queue[0]["workflow_source"] == "manual"


def test_workflow_run_appends_to_existing_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    queue_path = tmp_path / ".config" / "pkm" / "task_queue.json"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    existing_task = {"type": "task", "id": "existing_123", "task_type": "ask"}
    queue_path.write_text(json.dumps([existing_task]))

    runner = CliRunner()
    result = runner.invoke(main, ["workflow", "run", "zettelkasten_maintenance"])
    assert result.exit_code == 0

    queue = json.loads(queue_path.read_text())
    assert isinstance(queue, list)
    assert len(queue) == 2
    assert queue[0]["id"] == "existing_123"
    assert queue[1]["task_type"] == "workflow"
    assert queue[1]["workflow_id"] == "zettelkasten_maintenance"
    assert queue[1]["workflow_source"] == "manual"


def test_workflow_history_defaults_to_all_and_renders_recent_rows(tmp_path):
    """History command reads vault-local workflow runs and defaults to all workflows."""
    vault = VaultConfig(name="work", path=tmp_path / "vaults" / "work")
    append_workflow_history(
        vault.path,
        {
            "workflow_id": "weekly",
            "task_id": "task-1",
            "hostname": "host-a",
            "time": "2026-05-10T01:00:00Z",
            "status": "success",
            "source": "manual",
            "phase": "complete",
            "error": None,
            "result_summary": "created hub notes",
        },
    )
    append_workflow_history(
        vault.path,
        {
            "workflow_id": "nightly",
            "task_id": "task-2",
            "hostname": "host-b",
            "time": "2026-05-10T02:00:00Z",
            "status": "failure",
            "source": "scheduled",
            "phase": "agent",
            "error": "model failed",
            "result_summary": "agent stopped",
        },
    )

    runner = CliRunner()
    default_result = runner.invoke(workflow_group, ["history"], obj={"vault": vault})
    explicit_result = runner.invoke(
        workflow_group, ["history", "all"], obj={"vault": vault}
    )

    assert default_result.exit_code == 0, default_result.output
    assert explicit_result.exit_code == 0, explicit_result.output
    assert "weekly" in default_result.output
    assert "nightly" in default_result.output
    assert "model failed" in default_result.output
    assert default_result.output == explicit_result.output


def test_workflow_history_filters_limits_and_outputs_json(tmp_path):
    """History command supports workflow filtering, limits, JSON, and explicit vaults."""
    vault = tmp_path / "vault"
    append_workflow_history(
        vault,
        {
            "workflow_id": "weekly",
            "task_id": "older",
            "hostname": "host-a",
            "time": "2026-05-10T01:00:00Z",
            "status": "success",
            "source": "manual",
            "phase": "complete",
            "error": None,
            "result_summary": "older weekly",
        },
    )
    append_workflow_history(
        vault,
        {
            "workflow_id": "weekly",
            "task_id": "newer",
            "hostname": "host-a",
            "time": "2026-05-10T02:00:00Z",
            "status": "success",
            "source": "manual",
            "phase": "complete",
            "error": None,
            "result_summary": "newer weekly",
        },
    )
    append_workflow_history(
        vault,
        {
            "workflow_id": "nightly",
            "task_id": "other",
            "hostname": "host-b",
            "time": "2026-05-10T03:00:00Z",
            "status": "success",
            "source": "scheduled",
            "phase": "complete",
            "error": None,
            "result_summary": "other workflow",
        },
    )

    runner = CliRunner()
    result = runner.invoke(
        workflow_group,
        [
            "history",
            "weekly",
            "--limit",
            "1",
            "--format",
            "json",
            "--vault",
            str(vault),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert [record["task_id"] for record in payload] == ["newer"]


def test_workflow_history_empty_state_exits_zero(tmp_path):
    """Empty history is an operational state, not an error."""
    vault = VaultConfig(name="empty", path=tmp_path / "empty")
    runner = CliRunner()

    result = runner.invoke(workflow_group, ["history"], obj={"vault": vault})

    assert result.exit_code == 0, result.output
    assert "No workflow history" in result.output
