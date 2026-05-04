"""Workflow REST handlers."""

from __future__ import annotations

import json
import re
from typing import Any

from aiohttp import web

from pkm.web.routes.notes import _resolve_vault
from pkm.workflows import WorkflowConfig, load_workflows

_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):00$")


def _workflow_title(workflow_id: str) -> str:
    return workflow_id.replace("_", " ")


def _workflow_snippet(config: WorkflowConfig) -> str:
    text = " ".join(config.system_prompt_template.split())
    return text[:180] + ("..." if len(text) > 180 else "")


def _trigger_time(schedule_hour: int) -> str:
    return f"{schedule_hour:02d}:00"


def _workflow_payload(config: WorkflowConfig, *, include_body: bool = False) -> dict[str, Any]:
    payload = {
        "id": config.id,
        "title": _workflow_title(config.id),
        "schedule_hour": config.schedule_hour,
        "trigger_time": _trigger_time(config.schedule_hour),
        "enabled": config.enabled,
        "marker_file": config.marker_file,
        "pre_hook": config.pre_hook,
        "post_hook": config.post_hook,
        "snippet": _workflow_snippet(config),
    }
    if include_body:
        payload["body"] = config.system_prompt_template
        payload["jitter_type"] = config.jitter_type
    return payload


def _workflow_map(vault_path) -> dict[str, WorkflowConfig]:
    return {workflow.id: workflow for workflow in load_workflows(vault_path=vault_path)}


def _read_vault_overrides(path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_vault_override(vault, workflow_id: str, updates: dict[str, Any]) -> None:
    override_path = vault.pkm_dir / "workflow.json"
    overrides = _read_vault_overrides(override_path)
    by_id = {
        str(item.get("id")): item
        for item in overrides
        if isinstance(item, dict) and item.get("id")
    }
    current = by_id.get(workflow_id, {"id": workflow_id})
    by_id[workflow_id] = {**current, **updates}
    vault.pkm_dir.mkdir(parents=True, exist_ok=True)
    override_path.write_text(
        json.dumps(list(by_id.values()), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _parse_trigger_time(value: Any) -> int:
    if not isinstance(value, str):
        raise web.HTTPBadRequest(reason="trigger_time must be HH:00")
    match = _TIME_PATTERN.match(value)
    if not match:
        raise web.HTTPBadRequest(reason="trigger_time must be HH:00")
    return int(match.group(1))


async def list_workflows(request: web.Request) -> web.Response:
    vault = _resolve_vault(request.match_info["name"])
    workflows = load_workflows(vault_path=vault.path)
    return web.json_response([_workflow_payload(workflow) for workflow in workflows])


async def get_workflow(request: web.Request) -> web.Response:
    vault = _resolve_vault(request.match_info["name"])
    workflow_id = request.match_info["id"]
    workflows = _workflow_map(vault.path)
    workflow = workflows.get(workflow_id)
    if workflow is None:
        raise web.HTTPNotFound(reason=f"Workflow '{workflow_id}' not found")
    return web.json_response(_workflow_payload(workflow, include_body=True))


async def update_workflow(request: web.Request) -> web.Response:
    vault = _resolve_vault(request.match_info["name"])
    workflow_id = request.match_info["id"]
    workflows = _workflow_map(vault.path)
    workflow = workflows.get(workflow_id)
    if workflow is None:
        raise web.HTTPNotFound(reason=f"Workflow '{workflow_id}' not found")

    body = await request.json()
    updates: dict[str, Any] = {}
    if "enabled" in body:
        updates["enabled"] = bool(body["enabled"])
    if "trigger_time" in body:
        updates["schedule_hour"] = _parse_trigger_time(body["trigger_time"])
    if "schedule_hour" in body:
        hour = int(body["schedule_hour"])
        if hour < 0 or hour > 23:
            raise web.HTTPBadRequest(reason="schedule_hour must be 0-23")
        updates["schedule_hour"] = hour
    if not updates:
        return web.json_response(_workflow_payload(workflow, include_body=True))

    _write_vault_override(vault, workflow_id, updates)
    updated = _workflow_map(vault.path)[workflow_id]
    return web.json_response(_workflow_payload(updated, include_body=True))
