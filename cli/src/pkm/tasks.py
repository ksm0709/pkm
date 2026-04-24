"""Task extraction utilities for daily notes."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from pkm.config import VaultConfig

_STATUS_TAGS = frozenset({"TODO", "WIP", "DONE", "CANCEL", "P0", "P1", "P2", "P3"})


def _section_owner_matches(header: str, patterns: list[str]) -> bool | None:
    """Return True if header has a matching name tag, False if mismatched, None if no name tag."""
    tags = re.findall(r"#([A-Za-z][A-Za-z0-9]+)", header)
    name_tags = [t for t in tags if t not in _STATUS_TAGS]
    if not name_tags:
        return None  # no owner tag → public section
    for tag in name_tags:
        for pattern in patterns:
            if pattern.lower() in tag.lower():
                return True
    return False


def _detect_status(line: str, task_statuses: dict) -> str | None:
    """Detect task status from a line. Returns status key or None."""
    # Checkbox patterns take priority
    checkbox_map = {}
    for status_key, markers in task_statuses.items():
        for marker in markers:
            if marker.startswith("[") and marker.endswith("]"):
                checkbox_map[marker] = status_key

    # Check checkbox: "- [x] text" or "- [ ] text" etc.
    cb_match = re.match(r"^\s*-\s+(\[.?\])", line)
    if cb_match:
        cb = cb_match.group(1)
        if cb in checkbox_map:
            return checkbox_map[cb]

    # Check inline tags (#TODO, #WIP etc.)
    tag_map = {}
    for status_key, markers in task_statuses.items():
        for marker in markers:
            if not (marker.startswith("[") and marker.endswith("]")):
                tag_map[marker.upper()] = status_key

    for tag, status_key in tag_map.items():
        if f"#{tag}" in line.upper():
            return status_key

    return None


def _extract_item_text(line: str) -> str:
    """Extract the text content of a task item, stripping leading - and checkbox."""
    text = re.sub(r"^\s*-\s+\[.?\]\s*", "", line)
    text = re.sub(r"^\s*-\s+", "", text)
    # Strip status inline tags
    text = re.sub(r"#(TODO|WIP|DONE|CANCEL)\b", "", text, flags=re.IGNORECASE)
    return text.strip()


def _parse_tasks_from_text(
    text: str,
    task_statuses: dict,
    assignee_patterns: list[str],
) -> dict[str, list[str]]:
    """Parse task items from markdown text. Returns {status_key: [item_text]}."""
    result: dict[str, list[str]] = {k: [] for k in task_statuses}

    lines = text.splitlines()
    current_section_included = (
        True  # top-level content before any ## header is included
    )

    for line in lines:
        # Detect section header
        if line.startswith("## "):
            if not assignee_patterns:
                current_section_included = True
            else:
                owner_match = _section_owner_matches(line, assignee_patterns)
                current_section_included = owner_match is not False
            continue

        if not current_section_included:
            continue

        # Skip non-list lines (but allow indented sub-items)
        if not re.match(r"^\s*-\s+", line):
            continue

        status = _detect_status(line, task_statuses)
        if status is not None:
            item_text = _extract_item_text(line)
            if item_text:
                result[status].append(item_text)

    return result


def extract_tasks(vault: VaultConfig, scan_days: int = 3) -> dict[str, list[str]]:
    """Extract task items from recent daily notes and their subnotes.

    Scans the last `scan_days` days of daily notes plus YYYY-MM-DD-*.md subnotes.
    Applies section owner filtering via vault.task_assignee_patterns.
    Returns {status_key: [item_text]} dict.
    """
    result: dict[str, list[str]] = {k: [] for k in vault.task_statuses}
    today = date.today()

    for days_ago in range(scan_days):
        target_date = today - timedelta(days=days_ago)
        date_str = str(target_date)

        # Main daily note
        daily_path = vault.daily_dir / f"{date_str}.md"
        paths_to_scan: list[Path] = []
        if daily_path.exists():
            paths_to_scan.append(daily_path)

        # Subnotes: YYYY-MM-DD-*.md (exclude the daily note itself)
        if vault.daily_dir.is_dir():
            for p in sorted(vault.daily_dir.glob(f"{date_str}-*.md")):
                paths_to_scan.append(p)

        for path in paths_to_scan:
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            items = _parse_tasks_from_text(
                text, vault.task_statuses, vault.task_assignee_patterns
            )
            for status_key, item_list in items.items():
                result[status_key].extend(item_list)

    return result
