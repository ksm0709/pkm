"""Shared editor resolution for PKM CLI."""

from __future__ import annotations

import os


def get_editor(config_data: dict) -> str:
    """Resolve editor command: config → $VISUAL → $EDITOR → nano."""
    editor = config_data.get("defaults", {}).get("editor")
    if editor:
        return editor
    visual = os.environ.get("VISUAL")
    if visual:
        return visual
    env_editor = os.environ.get("EDITOR")
    if env_editor:
        return env_editor
    return "nano"
