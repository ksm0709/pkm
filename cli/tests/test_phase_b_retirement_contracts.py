"""Phase B vertical-slice-1 acceptance tests for retired public surfaces.

These tests intentionally describe the post-removal CLI, MCP, and REST contracts.
They are expected to be RED until the embedded Ask and Workflow surfaces are removed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig, WebConfig
from pkm.web.routes import configs as configs_route
from pkm.web.server import make_app

TOKEN = "phase-b-retirement-token"
AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def web_cfg(tmp_path: Path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7440, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def app(web_cfg: WebConfig):
    return make_app(web_config=web_cfg)


def test_cli_root_help_excludes_retired_commands_and_keeps_primitives() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    expected_discovery = {
        "mcp": True,
        "search": True,
        "index": True,
        "note": True,
        "daily": True,
        "ask": False,
        "workflow": False,
    }
    assert {
        command: f"\n  {command}" in result.output for command in expected_discovery
    } == expected_discovery


@pytest.mark.parametrize("command", ["ask", "workflow"])
def test_cli_retired_commands_use_click_unknown_command_behavior(command: str) -> None:
    result = CliRunner().invoke(main, [command])

    assert result.exit_code == 2
    assert f"No such command '{command}'" in result.output


@pytest.mark.anyio
async def test_mcp_tools_list_omits_ask_and_keeps_public_primitives() -> None:
    from pkm.mcp_server import mcp

    tools = await mcp.list_tools()
    tool_names = {tool.name for tool in tools}

    assert tool_names == {
        "add_wikilink",
        "create_daily_subnote",
        "create_hub_note",
        "daily_add",
        "find_backlinks_for_note",
        "find_surprising_connections",
        "get_note_neighbors",
        "index",
        "list_clusters",
        "list_consolidation_candidates",
        "list_god_nodes",
        "list_notes",
        "list_orphans",
        "list_stale_notes",
        "list_tags",
        "mark_consolidated",
        "note_add",
        "patch_note",
        "read_daily_log",
        "read_note",
        "read_recent_note_activity",
        "rename_note",
        "search",
        "tag_search",
        "vault_stats",
    }

    retired_schema_properties = {
        "ask",
        "ask_run_id",
        "credential",
        "credentials",
        "max_turns",
        "model",
        "provider",
        "reasoning_effort",
        "task_type",
        "workflow_id",
    }

    def property_names(schema: object) -> set[str]:
        if isinstance(schema, dict):
            names = set(schema.get("properties", {}))
            for value in schema.values():
                names.update(property_names(value))
            return names
        if isinstance(schema, list):
            names: set[str] = set()
            for value in schema:
                names.update(property_names(value))
            return names
        return set()

    leaked = {
        tool.name: sorted(property_names(tool.inputSchema) & retired_schema_properties)
        for tool in tools
        if property_names(tool.inputSchema) & retired_schema_properties
    }
    assert leaked == {}


@pytest.mark.anyio
async def test_authenticated_ask_routes_are_not_found(
    app, tmp_vault: VaultConfig
) -> None:
    run_id = "phase-b-retirement-probe"

    async with TestClient(TestServer(app)) as client:
        post_ask = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={"query": "probe", "ask_run_id": run_id},
            headers=AUTH_HEADERS,
        )
        await post_ask.read()
        options = await client.get(
            "/api/v1/vault/test-vault/ask/options",
            headers=AUTH_HEADERS,
        )
        await options.read()
        run = await client.get(
            f"/api/v1/vault/test-vault/ask/runs/{run_id}",
            headers=AUTH_HEADERS,
        )
        await run.read()
        vaults = await client.get("/api/v1/vaults", headers=AUTH_HEADERS)
        await vaults.read()

    assert {
        "post_ask": post_ask.status,
        "options": options.status,
        "known_run": run.status,
        "retained_vaults": vaults.status,
    } == {
        "post_ask": 404,
        "options": 404,
        "known_run": 404,
        "retained_vaults": 200,
    }


@pytest.mark.anyio
async def test_authenticated_workflow_routes_are_not_found(
    app, tmp_vault: VaultConfig
) -> None:
    workflow_id = "zettelkasten_maintenance"

    async with TestClient(TestServer(app)) as client:
        root_history = await client.get(
            "/api/v1/vault/test-vault/workflow-history",
            headers=AUTH_HEADERS,
        )
        await root_history.read()
        workflows = await client.get(
            "/api/v1/vault/test-vault/workflows",
            headers=AUTH_HEADERS,
        )
        await workflows.read()
        detail = await client.get(
            f"/api/v1/vault/test-vault/workflows/{workflow_id}",
            headers=AUTH_HEADERS,
        )
        await detail.read()
        update = await client.patch(
            f"/api/v1/vault/test-vault/workflows/{workflow_id}",
            json={"enabled": False},
            headers=AUTH_HEADERS,
        )
        await update.read()
        run = await client.post(
            f"/api/v1/vault/test-vault/workflows/{workflow_id}/run",
            headers=AUTH_HEADERS,
        )
        await run.read()
        run_status = await client.get(
            f"/api/v1/vault/test-vault/workflows/{workflow_id}/run-status",
            headers=AUTH_HEADERS,
        )
        await run_status.read()
        history = await client.get(
            f"/api/v1/vault/test-vault/workflows/{workflow_id}/history",
            headers=AUTH_HEADERS,
        )
        await history.read()
        vaults = await client.get("/api/v1/vaults", headers=AUTH_HEADERS)
        await vaults.read()

    assert {
        "root_history": root_history.status,
        "workflows": workflows.status,
        "detail": detail.status,
        "update": update.status,
        "run": run.status,
        "run_status": run_status.status,
        "history": history.status,
        "retained_vaults": vaults.status,
    } == {
        "root_history": 404,
        "workflows": 404,
        "detail": 404,
        "update": 404,
        "run": 404,
        "run_status": 404,
        "history": 404,
        "retained_vaults": 200,
    }


@pytest.mark.anyio
async def test_shared_configs_retire_only_ask_model_and_credential_branches(
    app, tmp_vault: VaultConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = {"defaults": {"vault": "test-vault", "model": "legacy-model"}}

    monkeypatch.setattr(configs_route, "load_config", lambda: config)
    monkeypatch.setattr(configs_route, "save_config", lambda updated: config.update(updated))

    async with TestClient(TestServer(app)) as client:
        configs = await client.get(
            "/api/v1/vault/test-vault/configs",
            headers=AUTH_HEADERS,
        )
        configs_body = await configs.json()
        model = await client.patch(
            "/api/v1/vault/test-vault/configs/settings/model",
            json={"value": "gpt-4o-mini"},
            headers=AUTH_HEADERS,
        )
        await model.read()
        reasoning_effort = await client.patch(
            "/api/v1/vault/test-vault/configs/settings/reasoning-effort",
            json={"value": "high"},
            headers=AUTH_HEADERS,
        )
        await reasoning_effort.read()
        put_credential = await client.put(
            "/api/v1/vault/test-vault/configs/ask/credentials/openai",
            json={"api_key": "retired-secret"},
            headers=AUTH_HEADERS,
        )
        await put_credential.read()
        delete_credential = await client.delete(
            "/api/v1/vault/test-vault/configs/ask/credentials/openai",
            headers=AUTH_HEADERS,
        )
        await delete_credential.read()
        vaults = await client.get("/api/v1/vaults", headers=AUTH_HEADERS)
        await vaults.read()

    assert {
        "configs": configs.status,
        "has_ask_credentials": "ask_credentials" in configs_body,
        "has_model_setting": any(
            setting["key"] == "model" for setting in configs_body["settings"]
        ),
        "has_reasoning_effort_setting": any(
            setting["key"] == "reasoning-effort"
            for setting in configs_body["settings"]
        ),
        "model_setting": model.status,
        "reasoning_effort_setting": reasoning_effort.status,
        "put_credential": put_credential.status,
        "delete_credential": delete_credential.status,
        "retained_vaults": vaults.status,
    } == {
        "configs": 200,
        "has_ask_credentials": False,
        "has_model_setting": False,
        "has_reasoning_effort_setting": False,
        "model_setting": 404,
        "reasoning_effort_setting": 404,
        "put_credential": 404,
        "delete_credential": 404,
        "retained_vaults": 200,
    }
