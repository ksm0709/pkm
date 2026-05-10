"""Workflow REST handlers."""

from __future__ import annotations

import json
import re
import socket
import time
from datetime import datetime, timezone
from typing import Any

from aiohttp import web

from pkm.credential_store import agent_credential_env
from pkm.web.routes.ask import _runtime_daemon_module
from pkm.web.routes.notes import _resolve_vault
from pkm.workflows import WorkflowConfig, load_workflows
from pkm.workflows.history import append_workflow_history, read_workflow_history

_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):00$")


def _workflow_title(workflow_id: str) -> str:
    return workflow_id.replace("_", " ")


def _workflow_snippet(config: WorkflowConfig) -> str:
    text = " ".join(config.system_prompt_template.split())
    return text[:180] + ("..." if len(text) > 180 else "")


def _trigger_time(schedule_hour: int) -> str:
    return f"{schedule_hour:02d}:00"


def _workflow_payload(
    config: WorkflowConfig, *, include_body: bool = False
) -> dict[str, Any]:
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


def _workflow_task_status(workflow_id: str) -> dict[str, Any]:
    daemon = _runtime_daemon_module()
    current = getattr(daemon.DaemonState, "current_task", None)
    if (
        isinstance(current, dict)
        and current.get("task_type") == "workflow"
        and current.get("workflow_id") == workflow_id
    ):
        return {"status": "running", "task_id": current.get("id")}

    queue = getattr(getattr(daemon, "task_queue", None), "queue", [])
    if isinstance(queue, list):
        for task in queue:
            if (
                isinstance(task, dict)
                and task.get("task_type") == "workflow"
                and task.get("workflow_id") == workflow_id
            ):
                return {"status": "queued", "task_id": task.get("id")}

    return {"status": "idle", "task_id": None}


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


def _history_limit(request: web.Request) -> int:
    raw = request.query.get("limit", "20")
    try:
        limit = int(raw)
    except ValueError:
        raise web.HTTPBadRequest(reason="limit must be an integer")
    if limit < 1:
        raise web.HTTPBadRequest(reason="limit must be >= 1")
    return limit


async def list_workflow_history(request: web.Request) -> web.Response:
    vault = _resolve_vault(request.match_info["name"])
    return web.json_response(
        read_workflow_history(vault.path, limit=_history_limit(request))
    )


async def get_workflow(request: web.Request) -> web.Response:
    vault = _resolve_vault(request.match_info["name"])
    workflow_id = request.match_info["id"]
    workflows = _workflow_map(vault.path)
    workflow = workflows.get(workflow_id)
    if workflow is None:
        raise web.HTTPNotFound(reason=f"Workflow '{workflow_id}' not found")
    return web.json_response(_workflow_payload(workflow, include_body=True))


async def get_workflow_history(request: web.Request) -> web.Response:
    vault = _resolve_vault(request.match_info["name"])
    workflow_id = request.match_info["id"]
    workflows = _workflow_map(vault.path)
    if workflow_id not in workflows:
        raise web.HTTPNotFound(reason=f"Workflow '{workflow_id}' not found")
    return web.json_response(
        read_workflow_history(
            vault.path,
            workflow_id=workflow_id,
            limit=_history_limit(request),
        )
    )


async def get_workflow_run_status(request: web.Request) -> web.Response:
    vault = _resolve_vault(request.match_info["name"])
    workflow_id = request.match_info["id"]
    workflows = _workflow_map(vault.path)
    if workflow_id not in workflows:
        raise web.HTTPNotFound(reason=f"Workflow '{workflow_id}' not found")
    return web.json_response(_workflow_task_status(workflow_id))


async def run_workflow(request: web.Request) -> web.Response:
    vault = _resolve_vault(request.match_info["name"])
    workflow_id = request.match_info["id"]
    workflows = _workflow_map(vault.path)
    if workflow_id not in workflows:
        raise web.HTTPNotFound(reason=f"Workflow '{workflow_id}' not found")

    daemon = _runtime_daemon_module()
    task_queue = getattr(daemon, "task_queue", None)
    if task_queue is None or not hasattr(task_queue, "push"):
        raise web.HTTPServiceUnavailable(reason="Task queue not initialized")

    task_id = f"{workflow_id}_manual_{time.time_ns()}"
    task = {
        "type": "task",
        "id": task_id,
        "task_type": "workflow",
        "workflow_id": workflow_id,
        "workflow_source": "manual",
        "env_keys": agent_credential_env(),
        "env": {"PKM_VAULT_DIR": str(vault.path)},
    }
    task_queue.push(task)
    append_workflow_history(
        vault.path,
        {
            "workflow_id": workflow_id,
            "task_id": task_id,
            "hostname": socket.gethostname(),
            "time": datetime.now(timezone.utc).isoformat(),
            "status": "queued",
            "source": "manual",
            "phase": "queued",
            "error": None,
            "result_summary": "Queued manual workflow run from web.",
        },
    )
    return web.json_response({"status": "queued", "task_id": task_id})


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
