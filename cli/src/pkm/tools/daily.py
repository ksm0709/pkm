import os
from pathlib import Path
from datetime import datetime
from tiny_agent.tools import tool
from pkm.config import VaultConfig
from pkm.commands.daily import add_daily_entry


def _get_vault(vault_dir: str) -> VaultConfig:
    path = Path(vault_dir)
    return VaultConfig(name=path.name, path=path)


@tool()
def add_daily_log(text: str) -> str:
    """Append a timestamped log entry to today's daily note.

    Args:
        text: The text to log.
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)

    try:
        entry = add_daily_entry(vault, text)
        return f"Successfully added daily log: {entry.strip()}"
    except Exception as e:
        return f"Error adding daily log: {str(e)}"


@tool()
def read_daily_log(date_str: str | None = None) -> str:
    """Read the daily note for a specific date.

    Args:
        date_str: The date in YYYY-MM-DD format. Defaults to today.
    """
    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)

    target_date = date_str or datetime.now().strftime("%Y-%m-%d")
    note_path = vault.daily_dir / f"{target_date}.md"

    if not note_path.exists():
        return f"No daily note found for {target_date}"

    try:
        return note_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading daily note: {str(e)}"


@tool()
def create_daily_subnote(title: str, content: str) -> str:
    """Create a subnote file for today and link it from today's daily note.

    Creates YYYY-MM-DD-{title}.md in the daily directory with the given content,
    then appends a [[wikilink]] timestamped entry to today's daily note.

    Args:
        title: Subnote title slug (spaces will be replaced with hyphens).
        content: Markdown content for the subnote body.
    """
    import re as _re
    from datetime import datetime as _dt
    from pkm.commands.daily import SUBNOTE_TEMPLATE, DAILY_TEMPLATE, _add_subnote_link

    v_dir = os.environ.get("PKM_VAULT_DIR", ".")
    vault = _get_vault(v_dir)

    try:
        today = _dt.now().strftime("%Y-%m-%d")
        now = _dt.now().strftime("%H:%M")

        # Sanitize title
        title_slug = _re.sub(r"[/\\]", "", title.replace(" ", "-"))
        title_slug = _re.sub(r"\.\.+", "", title_slug).strip("-").strip()
        if not title_slug:
            return "Error: title cannot be empty."

        note_id = f"{today}-{title_slug}"
        note_path = vault.daily_dir / f"{note_id}.md"

        # Guard against path traversal
        vault.daily_dir.mkdir(parents=True, exist_ok=True)
        if not str(note_path.resolve()).startswith(str(vault.daily_dir.resolve())):
            return "Error: invalid title — would escape daily directory."

        # Write subnote
        subnote_content = SUBNOTE_TEMPLATE.format(note_id=note_id) + content
        if not note_path.exists():
            note_path.write_text(subnote_content, encoding="utf-8")

        # Ensure today's daily note exists
        daily_path = vault.daily_dir / f"{today}.md"
        if not daily_path.exists():
            daily_path.write_text(DAILY_TEMPLATE.format(date=today), encoding="utf-8")

        # Add wikilink to daily note
        _add_subnote_link(daily_path, now, note_id)

        return f"Created subnote: {note_path.name}"
    except Exception as e:
        return f"Error creating subnote: {e}"
