"""Source-scoped annotation sidecar storage."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pkm.config import VaultConfig

AnnotationSourceKind = Literal["data", "note"]


@dataclass(frozen=True)
class AnnotationSource:
    """A single source whose annotations are stored as one sidecar document."""

    kind: AnnotationSourceKind
    identifier: str

    def __post_init__(self) -> None:
        if self.kind not in {"data", "note"}:
            raise ValueError("annotation source kind must be data or note")
        if not self.identifier:
            raise ValueError("annotation source identifier cannot be empty")

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.identifier}"

    def to_payload(self) -> dict:
        if self.kind == "data":
            return {"kind": "data", "path": self.identifier}
        return {"kind": "note", "note_id": self.identifier}


def empty_annotation_document(source: AnnotationSource) -> dict:
    """Return the canonical empty v2 document for *source*."""

    return {
        "version": 2,
        "source_key": source.key,
        "source": source.to_payload(),
        "annotations": [],
    }


def annotation_sidecar_path(vault: VaultConfig, source: AnnotationSource) -> Path:
    """Return the per-source annotation sidecar path under the vault .pkm dir."""

    root = (vault.path / ".pkm" / "annotations" / source.kind).resolve()
    digest = sha256(source.key.encode("utf-8")).hexdigest()
    target = (root / f"{digest}.json").resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("invalid annotation sidecar path") from exc
    return target


def read_annotation_document(vault: VaultConfig, source: AnnotationSource) -> dict:
    """Read the annotation document for *source*, or return an empty document."""

    path = annotation_sidecar_path(vault, source)
    if not path.is_file():
        return empty_annotation_document(source)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_annotation_document(
    vault: VaultConfig,
    source: AnnotationSource,
    document: dict,
) -> dict:
    """Atomically write one annotation document for *source*."""

    path = annotation_sidecar_path(vault, source)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp_name = handle.name
            json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)
    return document
