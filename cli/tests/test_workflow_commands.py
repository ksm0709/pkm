"""Tests for pkm workflow list/run CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import pytest
from pkm.cli import main
from pkm.commands.workflow import workflow_group
from pkm.config import VaultConfig


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
    assert "daily_task_summary" in ids


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
    result = runner.invoke(main, ["workflow", "run", "nonexistent_wf"])
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


def test_workflow_run_queues_task_with_injected_vault_env(tmp_path, monkeypatch):
    """Direct command use with a vault context queues the workflow for that vault path."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    vault = VaultConfig(name="work", path=tmp_path / "vaults" / "work")
    monkeypatch.setattr("pkm.commands.workflow.time.time", lambda: 42)

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
    result = runner.invoke(main, ["workflow", "run", "daily_task_summary"])

    assert result.exit_code == 0, result.output
    queue = json.loads(queue_path.read_text())
    assert isinstance(queue, list)
    assert len(queue) == 1
    assert queue[0]["task_type"] == "workflow"
    assert queue[0]["workflow_id"] == "daily_task_summary"


def test_workflow_run_appends_to_existing_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    queue_path = tmp_path / ".config" / "pkm" / "task_queue.json"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    existing_task = {"type": "task", "id": "existing_123", "task_type": "ask"}
    queue_path.write_text(json.dumps([existing_task]))

    runner = CliRunner()
    result = runner.invoke(main, ["workflow", "run", "daily_task_summary"])
    assert result.exit_code == 0

    queue = json.loads(queue_path.read_text())
    assert isinstance(queue, list)
    assert len(queue) == 2
    assert queue[0]["id"] == "existing_123"
    assert queue[1]["task_type"] == "workflow"
    assert queue[1]["workflow_id"] == "daily_task_summary"
