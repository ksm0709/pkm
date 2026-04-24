"""Tests for pkm workflow list/run CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from pkm.cli import main


def _write_workflow_json(path: Path, entries: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")


def test_workflow_list_shows_bundled_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["workflow", "list"])
    assert result.exit_code == 0
    # Bundled defaults should always be present (rich may truncate long IDs)
    assert "zettelkas" in result.output
    assert "daily_task" in result.output


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
    assert "my_wf" in result.output
    assert "3" in result.output


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
