"""Check for newer pkm releases on GitHub, with 24-hour caching."""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

GITHUB_REPO = "ksm0709/pkm"
CACHE_FILE = Path.home() / ".cache" / "pkm" / "version_check.json"
CACHE_TTL = 86400  # 24 hours
FETCH_TIMEOUT = 2  # seconds


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except ValueError:
        return (0,)


def _fetch_latest() -> str | None:
    """Fetch latest release tag from GitHub. Returns None on any failure."""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        with urlopen(url, timeout=FETCH_TIMEOUT) as resp:
            return json.loads(resp.read()).get("tag_name")
    except (URLError, json.JSONDecodeError, Exception):
        return None


def get_latest_version() -> str | None:
    """Return latest release tag, using 24h local cache."""
    try:
        if CACHE_FILE.exists():
            cached = json.loads(CACHE_FILE.read_text())
            if time.time() - cached.get("checked_at", 0) < CACHE_TTL:
                return cached.get("latest")
    except (json.JSONDecodeError, OSError):
        pass

    latest = _fetch_latest()
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps({"latest": latest, "checked_at": time.time()}))
    except OSError:
        pass
    return latest


def get_recent_versions(n: int = 5) -> list[str]:
    """Return up to n recent release tags from GitHub, newest first."""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page={n}"
        with urlopen(url, timeout=FETCH_TIMEOUT) as resp:
            releases = json.loads(resp.read())
            return [r["tag_name"] for r in releases if r.get("tag_name")]
    except (URLError, json.JSONDecodeError, Exception):
        return []


def available_update(current_version: str) -> str | None:
    """Return the newer version tag if one is available, else None."""
    latest = get_latest_version()
    if not latest:
        return None
    if _parse_version(latest) > _parse_version(current_version):
        return latest
    return None
