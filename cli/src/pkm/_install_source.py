"""Shared helper: locate or download the pkm cli source directory."""

from __future__ import annotations

import tarfile
import tempfile
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

GITHUB_REPO = "ksm0709/pkm"


def find_local_cli_dir() -> Path | None:
    """Walk up from this file until a directory containing pyproject.toml is found."""
    d = Path(__file__).parent
    while d != d.parent:
        if (d / "pyproject.toml").exists():
            return d
        d = d.parent
    return None


@contextmanager
def cli_source() -> Generator[tuple[Path, bool], None, None]:
    """Yield ``(cli_dir, is_local)``.

    *is_local=True*: ``cli_dir`` is the on-disk clone; the caller may pass
    ``--editable`` to uv.

    *is_local=False*: ``cli_dir`` is inside a temporary directory that is
    cleaned up when this context manager exits.  The caller must NOT use
    ``--editable`` (the source won't persist after install).
    """
    local = find_local_cli_dir()
    if local is not None:
        yield local, True
        return

    tarball_url = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/main.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        tarball_path = Path(tmp) / "pkm.tar.gz"
        urllib.request.urlretrieve(tarball_url, tarball_path)
        with tarfile.open(tarball_path, "r:gz") as tf:
            tf.extractall(tmp)
        extracted = [
            p for p in Path(tmp).iterdir() if p.is_dir() and p.name != "__MACOSX"
        ]
        if not extracted:
            raise RuntimeError("Unexpected tarball layout from GitHub.")
        yield extracted[0] / "cli", False
