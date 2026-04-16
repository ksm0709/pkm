"""Trash directory helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pkm.config import get_vaults_root


def make_trash_path(name: str) -> Path:
    """Return a unique trash path under <vaults_root>/.trash/<name>-<timestamp>.

    Appends a numeric suffix when the timestamp already exists.
    """
    trash_parent = get_vaults_root() / ".trash"
    trash_parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    trash_path = trash_parent / f"{name}-{timestamp}"

    if trash_path.exists():
        counter = 1
        while True:
            candidate = trash_parent / f"{name}-{timestamp}-{counter}"
            if not candidate.exists():
                trash_path = candidate
                break
            counter += 1

    return trash_path
