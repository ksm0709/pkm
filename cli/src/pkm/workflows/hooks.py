"""Bundled pre/post hook implementations for PKM daemon workflows."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pkm.config import VaultConfig


def build_daily_summary(vault: "VaultConfig", today: str) -> dict:
    """Pre-hook for daily_task_summary workflow.

    Performs rollover of yesterday's WIP/TODO items into today's daily note,
    then builds a summary_content string grouped by status.

    Returns {'rollover_result': summary_content}.
    """
    from pkm.tasks import extract_tasks, _parse_tasks_from_text
    from pkm.commands.daily import DAILY_TEMPLATE

    tasks = extract_tasks(vault, scan_days=3)

    yesterday = str(date.fromisoformat(today) - timedelta(days=1))
    daily_dir = vault.daily_dir

    yesterday_paths: list[Path] = []
    if (daily_dir / f"{yesterday}.md").exists():
        yesterday_paths.append(daily_dir / f"{yesterday}.md")
    for p in sorted(daily_dir.glob(f"{yesterday}-*.md")):
        yesterday_paths.append(p)

    rollover_items: list[tuple[str, str]] = []
    for path in yesterday_paths:
        try:
            text = path.read_text(encoding="utf-8")
            day_tasks = _parse_tasks_from_text(
                text, vault.task_statuses, vault.task_assignee_patterns
            )
            for item in day_tasks.get("wip", []):
                rollover_items.append(("[>]", item))
            for item in day_tasks.get("todo", []):
                rollover_items.append(("[ ]", item))
        except Exception:
            pass

    if rollover_items:
        today_path = daily_dir / f"{today}.md"
        daily_dir.mkdir(parents=True, exist_ok=True)
        if not today_path.exists():
            today_path.write_text(DAILY_TEMPLATE.format(date=today), encoding="utf-8")
        content = today_path.read_text(encoding="utf-8")

        existing_todo_lines: set[str] = set()
        if "## TODO" in content:
            todo_body = content.split("## TODO", 1)[1]
            next_section = todo_body.find("\n## ")
            if next_section != -1:
                todo_body = todo_body[:next_section]
            existing_todo_lines = {
                ln.strip() for ln in todo_body.splitlines() if ln.strip()
            }

        new_items = []
        for marker, item in rollover_items:
            line = f"- {marker} {item}"
            if item and line.strip() not in existing_todo_lines:
                new_items.append(line)

        if new_items:
            insert = "\n".join(new_items) + "\n"
            if "## TODO" in content:
                content = content.replace("## TODO\n", f"## TODO\n{insert}", 1)
            else:
                content += f"\n## TODO\n{insert}"
            today_path.write_text(content, encoding="utf-8")

    status_emoji = {"wip": "[>]", "todo": "[ ]", "done": "[x]", "cancel": "[-]"}
    status_header = {
        "wip": "## WIP",
        "todo": "## TODO",
        "done": "## DONE",
        "cancel": "## CANCEL",
    }
    sections = []
    for status_key in ("wip", "todo", "done", "cancel"):
        items = tasks.get(status_key, [])
        if items:
            marker = status_emoji.get(status_key, "[ ]")
            lines = [status_header[status_key]]
            for item in items:
                lines.append(f"- {marker} {item}")
            sections.append("\n".join(lines))

    summary_content = "\n\n".join(sections) if sections else "_No tasks found._"
    return {"rollover_result": summary_content}
