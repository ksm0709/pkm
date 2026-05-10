"""Integration tests for workflow web API endpoints."""

from __future__ import annotations

import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import WebConfig
from pkm.web.server import make_app
from pkm.workflows.history import append_workflow_history, read_workflow_history

TOKEN = "test-workflow-token"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7420, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def app(web_cfg: WebConfig):
    return make_app(web_config=web_cfg)


@pytest.mark.anyio
async def test_list_workflows_returns_readable_workflow_summaries(app, tmp_vault):
    """Workflow list endpoint returns note-like summaries with trigger and enabled state."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/workflows",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()

    first = data[0]
    assert {item["id"] for item in data} >= {
        "zettelkasten_maintenance",
    }
    assert "daily_task_summary" not in {item["id"] for item in data}
    assert set(first) >= {
        "id",
        "title",
        "trigger_time",
        "schedule_hour",
        "enabled",
        "snippet",
    }
    assert first["enabled"] is True
    assert first["trigger_time"].endswith(":00")


@pytest.mark.anyio
async def test_get_workflow_returns_read_mode_body(app, tmp_vault):
    """Workflow detail endpoint includes the prompt body needed for read mode."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/workflows/zettelkasten_maintenance",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()

    assert data["id"] == "zettelkasten_maintenance"
    assert data["title"] == "zettelkasten maintenance"
    assert data["trigger_time"] == "02:00"
    assert data["enabled"] is True
    assert "Zettelkasten maintainer" in data["body"]


@pytest.mark.anyio
async def test_get_workflow_missing_id_returns_404(app, tmp_vault):
    """Unknown workflow detail requests return 404 with the missing id."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/workflows/nope",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert resp.status == 404
    assert "nope" in resp.reason


@pytest.mark.anyio
async def test_patch_workflow_persists_enabled_state_and_trigger_time(app, tmp_vault):
    """PATCH writes a vault override so workflow enabled and trigger time survive reload."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/workflows/zettelkasten_maintenance",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"enabled": False, "trigger_time": "06:00"},
        )
        assert resp.status == 200
        data = await resp.json()

        detail_resp = await client.get(
            "/api/v1/vault/test-vault/workflows/zettelkasten_maintenance",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert detail_resp.status == 200
        detail = await detail_resp.json()

    assert data["enabled"] is False
    assert data["trigger_time"] == "06:00"
    assert detail["enabled"] is False
    assert detail["trigger_time"] == "06:00"

    override_path = tmp_vault.path / ".pkm" / "workflow.json"
    overrides = json.loads(override_path.read_text(encoding="utf-8"))
    assert overrides == [
        {"id": "zettelkasten_maintenance", "enabled": False, "schedule_hour": 6}
    ]


@pytest.mark.anyio
async def test_patch_workflow_missing_id_returns_404_without_override(app, tmp_vault):
    """Unknown workflow updates fail without creating a vault override file."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/workflows/nope",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"enabled": False},
        )

    assert resp.status == 404
    assert "nope" in resp.reason
    assert not (tmp_vault.path / ".pkm" / "workflow.json").exists()


@pytest.mark.anyio
async def test_patch_workflow_noop_returns_detail_without_override(app, tmp_vault):
    """A PATCH with no editable fields returns detail data and skips persistence."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/workflows/zettelkasten_maintenance",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={},
        )
        assert resp.status == 200
        data = await resp.json()

    assert data["id"] == "zettelkasten_maintenance"
    assert "body" in data
    assert "jitter_type" in data
    assert not (tmp_vault.path / ".pkm" / "workflow.json").exists()


@pytest.mark.anyio
async def test_patch_workflow_rejects_invalid_trigger_time(app, tmp_vault):
    """Invalid trigger time must fail without writing a workflow override."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/workflows/zettelkasten_maintenance",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"trigger_time": "25:00"},
        )

    assert resp.status == 400
    assert not (tmp_vault.path / ".pkm" / "workflow.json").exists()


@pytest.mark.anyio
async def test_patch_workflow_rejects_non_string_trigger_time(app, tmp_vault):
    """Non-string trigger_time values are rejected before writing overrides."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/workflows/zettelkasten_maintenance",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"trigger_time": 7},
        )

    assert resp.status == 400
    assert not (tmp_vault.path / ".pkm" / "workflow.json").exists()


@pytest.mark.anyio
async def test_patch_workflow_rejects_out_of_range_schedule_hour(app, tmp_vault):
    """Out-of-range schedule_hour values fail without writing overrides."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/workflows/zettelkasten_maintenance",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"schedule_hour": 24},
        )

    assert resp.status == 400
    assert "schedule_hour must be 0-23" in resp.reason
    assert not (tmp_vault.path / ".pkm" / "workflow.json").exists()


@pytest.mark.anyio
@pytest.mark.parametrize("bad_override", ["{bad json", json.dumps({"id": "old"})])
async def test_patch_workflow_recovers_from_corrupt_override_file(
    app, tmp_vault, bad_override: str
):
    """Corrupt override state is replaced by a valid workflow override list."""
    override_path = tmp_vault.path / ".pkm" / "workflow.json"
    override_path.write_text(bad_override, encoding="utf-8")

    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/workflows/zettelkasten_maintenance",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"enabled": False},
        )
        assert resp.status == 200
        data = await resp.json()

    assert data["enabled"] is False
    assert json.loads(override_path.read_text(encoding="utf-8")) == [
        {"id": "zettelkasten_maintenance", "enabled": False}
    ]


@pytest.mark.anyio
async def test_workflow_history_endpoints_return_all_and_filtered_records(
    app, tmp_vault
):
    """Web history endpoints expose the same vault-local workflow history source."""
    append_workflow_history(
        tmp_vault.path,
        {
            "workflow_id": "zettelkasten_maintenance",
            "task_id": "task-1",
            "hostname": "host-a",
            "time": "2026-05-10T01:00:00Z",
            "status": "success",
            "source": "manual",
            "phase": "complete",
            "error": None,
            "result_summary": "repaired notes",
        },
    )
    append_workflow_history(
        tmp_vault.path,
        {
            "workflow_id": "custom_workflow",
            "task_id": "task-2",
            "hostname": "host-b",
            "time": "2026-05-10T02:00:00Z",
            "status": "failure",
            "source": "scheduled",
            "phase": "agent",
            "error": "model failed",
            "result_summary": "stopped early",
        },
    )

    async with TestClient(TestServer(app)) as client:
        all_resp = await client.get(
            "/api/v1/vault/test-vault/workflow-history",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        filtered_resp = await client.get(
            "/api/v1/vault/test-vault/workflows/zettelkasten_maintenance/history",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        detail_resp = await client.get(
            "/api/v1/vault/test-vault/workflows/zettelkasten_maintenance",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        all_records = await all_resp.json()
        filtered_records = await filtered_resp.json()

    assert all_resp.status == 200
    assert filtered_resp.status == 200
    assert detail_resp.status == 200

    assert [record["task_id"] for record in all_records] == ["task-2", "task-1"]
    assert [record["task_id"] for record in filtered_records] == ["task-1"]
    assert all_records[0]["error"] == "model failed"


@pytest.mark.anyio
async def test_workflow_history_endpoint_unknown_workflow_returns_404(app, tmp_vault):
    """Per-workflow history keeps the same unknown-id behavior as workflow detail."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/workflows/nope/history",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert resp.status == 404


@pytest.mark.anyio
async def test_run_workflow_queues_task_and_records_history(app, tmp_vault, monkeypatch):
    """Manual web runs use the daemon queue and leave an immediate audit record."""
    from pkm import daemon
    from pkm.workflows import load_workflows

    class Queue:
        def __init__(self):
            self.queue = []

        def push(self, task):
            self.queue.append(task)

    queue = Queue()
    workflow_id = load_workflows(vault_path=tmp_vault.path)[0].id
    monkeypatch.setattr(daemon, "task_queue", queue)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            f"/api/v1/vault/test-vault/workflows/{workflow_id}/run",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        data = await resp.json()

    assert resp.status == 200
    assert data["status"] == "queued"
    assert data["task_id"].startswith(f"{workflow_id}_manual_")
    assert queue.queue == [
        {
            "type": "task",
            "id": data["task_id"],
            "task_type": "workflow",
            "workflow_id": workflow_id,
            "workflow_source": "manual",
            "env": {"PKM_VAULT_DIR": str(tmp_vault.path)},
        }
    ]
    records = read_workflow_history(tmp_vault.path, workflow_id=workflow_id)
    assert records[0]["task_id"] == data["task_id"]
    assert records[0]["status"] == "queued"
    assert records[0]["phase"] == "queued"


@pytest.mark.anyio
async def test_workflow_run_status_reports_running_and_queued(
    app, tmp_vault, monkeypatch
):
    """Run status tells the UI whether this workflow is running, queued, or idle."""
    from pkm import daemon
    from pkm.workflows import load_workflows

    workflow_id = load_workflows(vault_path=tmp_vault.path)[0].id

    class Queue:
        queue = [
            {
                "id": "queued-task",
                "task_type": "workflow",
                "workflow_id": workflow_id,
            }
        ]

    monkeypatch.setattr(daemon, "task_queue", Queue())
    monkeypatch.setattr(
        daemon.DaemonState,
        "current_task",
        {
            "id": "running-task",
            "task_type": "workflow",
            "workflow_id": "other_workflow",
        },
    )

    async with TestClient(TestServer(app)) as client:
        queued_resp = await client.get(
            f"/api/v1/vault/test-vault/workflows/{workflow_id}/run-status",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        queued = await queued_resp.json()

    assert queued == {"status": "queued", "task_id": "queued-task"}

    monkeypatch.setattr(
        daemon.DaemonState,
        "current_task",
        {
            "id": "running-task",
            "task_type": "workflow",
            "workflow_id": workflow_id,
        },
    )
    async with TestClient(TestServer(app)) as client:
        running_resp = await client.get(
            f"/api/v1/vault/test-vault/workflows/{workflow_id}/run-status",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        running = await running_resp.json()

    assert running == {"status": "running", "task_id": "running-task"}
