"""Shared editor resolution for PKM CLI."""

from __future__ import annotations

import os
from typing import Any


def get_editor(config_data: dict[str, Any]) -> str:
    """Resolve editor command: config → $VISUAL → $EDITOR → nano."""
    return (
        config_data.get("defaults", {}).get("editor")
        or os.environ.get("VISUAL")
        or os.environ.get("EDITOR")
        or "nano"
    )
