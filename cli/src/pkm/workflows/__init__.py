"""Workflow configuration loading and hook resolution for PKM daemon."""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import socket
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class WorkflowConfig:
    id: str
    schedule_hour: int
    jitter_type: str
    marker_file: str
    system_prompt_template: str
    pre_hook: Optional[str] = None
    post_hook: Optional[str] = None
    enabled: bool = False


def _global_workflow_path() -> Path:
    return Path.home() / ".config" / "pkm" / "workflow.json"


def _vault_workflow_path(vault_path: str | Path) -> Path:
    return Path(vault_path) / ".pkm" / "workflow.json"


_BUNDLED_DEFAULTS = Path(__file__).parent / "default_workflows.json"
_REQUIRED_FIELDS = {"id", "schedule_hour", "marker_file"}
_MANAGED_DEFAULT_SYNC_FIELDS = ("system_prompt_template", "pre_hook", "post_hook")
_MANAGED_DEFAULT_FILL_FIELDS = ("enabled",)


def _merge_from_file(path: Path, entries: dict[str, dict[str, Any]]) -> None:
    if not path.exists():
        return
    try:
        for item in json.loads(path.read_text(encoding="utf-8")):
            item_id = item["id"]
            entries[item_id] = {**entries.get(item_id, {}), **item}
    except Exception:
        pass


def _load_workflow_items(path: Path) -> list[dict[str, Any]] | None:
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(items, list):
        return None
    return [item for item in items if isinstance(item, dict)]


def _bundled_workflows_by_id() -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    _merge_from_file(_BUNDLED_DEFAULTS, entries)
    return entries


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default
    return bool(value)


def _is_stale_zettelkasten_default(item: dict[str, Any]) -> bool:
    if item.get("id") != "zettelkasten_maintenance":
        return False

    prompt = item.get("system_prompt_template")
    if not isinstance(prompt, str):
        return False

    old_default_markers = (
        "CLUSTER DRIFT REVIEW" in prompt
        and "find_surprising_connections" in prompt
        and "create_hub_note" in prompt
    )
    stale_relation_markers = (
        "get_graph_context" in prompt
        or "get_note_neighbors" not in prompt
        or "&relation [[target]] - reason" not in prompt
    )
    return old_default_markers and stale_relation_markers


def _is_bundled_default_copy(item: dict[str, Any], default: dict[str, Any]) -> bool:
    if _is_stale_zettelkasten_default(item):
        return True
    prompt = item.get("system_prompt_template")
    default_prompt = default.get("system_prompt_template")
    return isinstance(prompt, str) and prompt == default_prompt


def _sync_bundled_workflow_item(
    item: dict[str, Any], default: dict[str, Any]
) -> bool:
    changed = False
    is_managed_copy = _is_bundled_default_copy(item, default)

    if is_managed_copy:
        for field in _MANAGED_DEFAULT_SYNC_FIELDS:
            if field in default:
                next_value = default[field]
                if item.get(field) != next_value:
                    item[field] = next_value
                    changed = True
            elif field in item:
                item.pop(field, None)
                changed = True

        for field in _REQUIRED_FIELDS:
            if field not in item:
                item[field] = default[field]
                changed = True
        if "jitter_type" not in item:
            item["jitter_type"] = default.get("jitter_type", "md5_hostname")
            changed = True

    if is_managed_copy:
        for field in _MANAGED_DEFAULT_FILL_FIELDS:
            if field not in item:
                item[field] = default.get(field, False)
                changed = True

    return changed


def sync_installed_workflow_defaults(path: Path | None = None) -> Path | None:
    """Refresh locally installed workflow defaults after package updates.

    Global workflow overrides intentionally win over bundled defaults. Older pkm
    installs copied the zettelkasten daemon prompt into ~/.config/pkm/workflow.json,
    so package updates alone cannot repair that prompt. This migration only
    updates recognizable bundled-default copies and fills new default fields,
    while preserving local scheduling choices.
    """
    workflow_path = path or _global_workflow_path()
    if not workflow_path.exists():
        return None

    items = _load_workflow_items(workflow_path)
    if items is None:
        return None

    defaults = _bundled_workflows_by_id()

    changed = False
    for item in items:
        item_id = item.get("id")
        if not isinstance(item_id, str):
            continue
        default = defaults.get(item_id)
        if default is None:
            continue
        changed = _sync_bundled_workflow_item(item, default) or changed

    if not changed:
        return None

    backup = workflow_path.with_name(
        f"{workflow_path.name}.bak-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    )
    backup.write_text(workflow_path.read_text(encoding="utf-8"), encoding="utf-8")
    workflow_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return workflow_path


def sync_stale_global_workflow_defaults(path: Path | None = None) -> Path | None:
    """Backward-compatible alias for older callers."""
    return sync_installed_workflow_defaults(path)


def load_workflows(vault_path: str | Path | None = None) -> list[WorkflowConfig]:
    """Load workflow definitions, merging vault overrides over global config.

    Priority: vault override > global ~/.config/pkm/workflow.json > bundled defaults.
    """
    entries: dict[str, dict[str, Any]] = {}
    _merge_from_file(_BUNDLED_DEFAULTS, entries)
    _merge_from_file(_global_workflow_path(), entries)
    if vault_path is not None:
        _merge_from_file(_vault_workflow_path(vault_path), entries)

    configs: list[WorkflowConfig] = []
    for e in entries.values():
        missing = sorted(field for field in _REQUIRED_FIELDS if field not in e)
        if missing:
            logger.warning(
                "Skipping incomplete workflow config '%s'; missing: %s",
                e.get("id", "<unknown>"),
                ", ".join(missing),
            )
            continue
        configs.append(
            WorkflowConfig(
                id=e["id"],
                schedule_hour=int(e["schedule_hour"]),
                jitter_type=e.get("jitter_type", "md5_hostname"),
                marker_file=e["marker_file"],
                system_prompt_template=e.get("system_prompt_template", ""),
                pre_hook=e.get("pre_hook") or None,
                post_hook=e.get("post_hook") or None,
                enabled=_coerce_bool(e.get("enabled"), default=False),
            )
        )
    return configs


def jitter_minutes(config: WorkflowConfig) -> int:
    """Compute deterministic 0-29 minute jitter for this host and workflow."""
    hostname = socket.gethostname()
    jt = config.jitter_type
    if jt == "md5_hostname":
        seed = hostname
    elif jt.startswith("md5_hostname_suffix:"):
        suffix = jt.split(":", 1)[1]
        seed = hostname + suffix
    else:
        seed = hostname + config.id
    return int(hashlib.md5(seed.encode()).hexdigest(), 16) % 30


def resolve_hook(module_path: Optional[str]) -> Optional[Callable]:
    """Resolve 'module:function' string to a callable, or return None."""
    if not module_path:
        return None
    module_name, func_name = module_path.rsplit(":", 1)
    mod = importlib.import_module(module_name)
    return getattr(mod, func_name)
