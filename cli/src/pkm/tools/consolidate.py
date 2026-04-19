import json
import os
from datetime import date
from pathlib import Path

from tiny_agent.tools import tool
from pkm.config import VaultConfig


def _get_vault(vault_dir: str) -> VaultConfig:
    return VaultConfig(name=Path(vault_dir).name, path=Path(vault_dir))


@tool()
def list_consolidation_candidates() -> str:
    """List daily notes eligible for Zettelkasten consolidation (not today, not already consolidated).

    Use when running a zettel-loop workflow or when the user asks which daily notes
    can be distilled into atomic notes. Returns JSON: {candidates: [{date, entry_count}], count}.
    """
    try:
        vault = _get_vault(os.environ.get("PKM_VAULT_DIR", "."))
        from pkm.commands.consolidate import _list_candidate_dates

        dates = _list_candidate_dates(vault)
        items = []
        for date_str in dates:
            md_file = vault.daily_dir / f"{date_str}.md"
            entry_count = 0
            try:
                text = md_file.read_text(encoding="utf-8")
                body_start = text.find("---", 3)
                body = text[body_start + 3 :] if body_start != -1 else text
                entry_count = sum(
                    1
                    for line in body.splitlines()
                    if line.strip().startswith(("-", "*", "["))
                )
            except Exception:
                pass
            items.append({"date": date_str, "entry_count": entry_count})
        return json.dumps({"candidates": items, "count": len(items)}, indent=2)
    except Exception as e:
        return f"Error: {e}"


@tool()
def mark_consolidated(date_str: str, distilled_note_ids: list[str]) -> str:
    """Mark a daily note as consolidated after distilling its insights into atomic notes.

    Use ONLY after the user has distilled insights from that daily note — this is a
    commit action. Requires distilled_note_ids: list of note IDs (stems) that were
    created during distillation. Validates all note IDs exist before marking.
    Records distilled_to field in frontmatter for auditability.
    Cannot mark today's date.
    """
    try:
        vault = _get_vault(os.environ.get("PKM_VAULT_DIR", "."))
        today = date.today().isoformat()

        if date_str == today:
            return "Error: Cannot mark today's daily note as consolidated — it is still in use."

        note_path = vault.daily_dir / f"{date_str}.md"
        if not note_path.exists():
            return f"Error: Daily note not found: {date_str}.md"

        # Validate all distilled note IDs exist
        missing = []
        for nid in distilled_note_ids:
            if not (vault.notes_dir / f"{nid}.md").exists():
                missing.append(nid)
        if missing:
            return f"Error: Distilled note IDs not found in vault: {', '.join(missing)}"

        from pkm.commands.consolidate import _parse_frontmatter, _set_frontmatter_field

        text = note_path.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        if fm.get("consolidated", False):
            return f"Already consolidated: {date_str}.md"

        text = _set_frontmatter_field(text, "consolidated", True)
        text = _set_frontmatter_field(text, "distilled_to", distilled_note_ids)
        note_path.write_text(text, encoding="utf-8")
        return json.dumps(
            {
                "status": "consolidated",
                "date": date_str,
                "distilled_to": distilled_note_ids,
            },
            indent=2,
        )
    except Exception as e:
        return f"Error: {e}"
