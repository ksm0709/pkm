"""Workflow configuration loading and hook resolution for PKM daemon."""

from __future__ import annotations

import hashlib
import importlib
import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class WorkflowConfig:
    id: str
    schedule_hour: int
    jitter_type: str
    marker_file: str
    system_prompt_template: str
    pre_hook: Optional[str] = None
    post_hook: Optional[str] = None


def _global_workflow_path() -> Path:
    return Path.home() / ".config" / "pkm" / "workflow.json"


def _vault_workflow_path(vault_path: str | Path) -> Path:
    return Path(vault_path) / ".pkm" / "workflow.json"


_BUNDLED_DEFAULTS = Path(__file__).parent / "default_workflows.json"


def _merge_from_file(path: Path, entries: dict[str, dict[str, Any]]) -> None:
    if not path.exists():
        return
    try:
        for item in json.loads(path.read_text(encoding="utf-8")):
            entries[item["id"]] = item
    except Exception:
        pass


def load_workflows(vault_path: str | Path | None = None) -> list[WorkflowConfig]:
    """Load workflow definitions, merging vault overrides over global config.

    Priority: vault override > global ~/.config/pkm/workflow.json > bundled defaults.
    """
    entries: dict[str, dict[str, Any]] = {}
    _merge_from_file(_BUNDLED_DEFAULTS, entries)
    _merge_from_file(_global_workflow_path(), entries)
    if vault_path is not None:
        _merge_from_file(_vault_workflow_path(vault_path), entries)

    return [
        WorkflowConfig(
            id=e["id"],
            schedule_hour=int(e["schedule_hour"]),
            jitter_type=e.get("jitter_type", "md5_hostname"),
            marker_file=e["marker_file"],
            system_prompt_template=e.get("system_prompt_template", ""),
            pre_hook=e.get("pre_hook") or None,
            post_hook=e.get("post_hook") or None,
        )
        for e in entries.values()
    ]


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
