"""Vault-local workflow execution history helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
HISTORY_FILENAME = "workflow-history.jsonl"


def workflow_history_path(vault_path: str | Path) -> Path:
    return Path(vault_path) / ".pkm" / HISTORY_FILENAME


def append_workflow_history(vault_path: str | Path, record: dict[str, Any]) -> None:
    path = workflow_history_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": SCHEMA_VERSION, **record}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def read_workflow_history(
    vault_path: str | Path,
    *,
    workflow_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []

    path = workflow_history_path(vault_path)
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        if workflow_id is not None and item.get("workflow_id") != workflow_id:
            continue
        records.append(item)

    return list(reversed(records))[:limit]
