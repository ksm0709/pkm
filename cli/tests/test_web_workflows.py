"""Integration tests for workflow web API endpoints."""

from __future__ import annotations

import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import WebConfig
from pkm.web.server import make_app

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
        "daily_task_summary",
    }
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
            "/api/v1/vault/test-vault/workflows/daily_task_summary",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()

    assert data["id"] == "daily_task_summary"
    assert data["title"] == "daily task summary"
    assert data["trigger_time"] == "08:00"
    assert data["enabled"] is True
    assert "create_daily_subnote" in data["body"]


@pytest.mark.anyio
async def test_patch_workflow_persists_enabled_state_and_trigger_time(app, tmp_vault):
    """PATCH writes a vault override so workflow enabled and trigger time survive reload."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/workflows/daily_task_summary",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"enabled": False, "trigger_time": "06:00"},
        )
        assert resp.status == 200
        data = await resp.json()

        detail_resp = await client.get(
            "/api/v1/vault/test-vault/workflows/daily_task_summary",
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
        {"id": "daily_task_summary", "enabled": False, "schedule_hour": 6}
    ]


@pytest.mark.anyio
async def test_patch_workflow_rejects_invalid_trigger_time(app, tmp_vault):
    """Invalid trigger time must fail without writing a workflow override."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/workflows/daily_task_summary",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"trigger_time": "25:00"},
        )

    assert resp.status == 400
    assert not (tmp_vault.path / ".pkm" / "workflow.json").exists()
