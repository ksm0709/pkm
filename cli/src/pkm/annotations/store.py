"""Source-scoped annotation sidecar storage."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
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


def _note_lifecycle_lock_path(vault: VaultConfig, note_id: str) -> Path:
    root = (vault.path / ".pkm" / "locks" / "note").resolve()
    digest = sha256(f"note:{note_id}".encode("utf-8")).hexdigest()
    return root / f"{digest}.lock"


@contextmanager
def note_lifecycle_lock(
    vault: VaultConfig,
    *note_ids: str,
) -> Iterator[None]:
    """Serialize note-file and note-annotation lifecycle mutations.

    Multiple note IDs are acquired in deterministic path order so rename can
    safely lock both the old and new identities without deadlocking CRUD routes.
    """

    lock_paths = sorted(
        {_note_lifecycle_lock_path(vault, note_id) for note_id in note_ids}
    )
    with ExitStack() as stack:
        for lock_path in lock_paths:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_file = stack.enter_context(lock_path.open("a+", encoding="utf-8"))
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            stack.callback(fcntl.flock, lock_file.fileno(), fcntl.LOCK_UN)
        yield


@contextmanager
def annotation_document_lock(
    vault: VaultConfig,
    source: AnnotationSource,
) -> Iterator[None]:
    """Hold the cross-process lock for one annotation sidecar transaction."""

    path = annotation_sidecar_path(vault, source)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def mutate_annotation_document(
    vault: VaultConfig,
    source: AnnotationSource,
    mutator: Callable[[dict], dict],
) -> dict:
    """Serialize a read-modify-write transaction for one annotation sidecar."""

    with annotation_document_lock(vault, source):
        current = read_annotation_document(vault, source)
        updated = mutator(current)
        return write_annotation_document(vault, source, updated)


def rename_annotation_document(
    vault: VaultConfig,
    old_source: AnnotationSource,
    new_source: AnnotationSource,
) -> bool:
    """Move one sidecar to a new source identity under ordered cross-process locks."""

    ordered_sources = sorted(
        (old_source, new_source),
        key=lambda source: str(annotation_sidecar_path(vault, source)),
    )
    with ExitStack() as stack:
        for source in ordered_sources:
            stack.enter_context(annotation_document_lock(vault, source))
        old_path = annotation_sidecar_path(vault, old_source)
        new_path = annotation_sidecar_path(vault, new_source)
        if new_path.exists():
            raise FileExistsError(
                f"Annotation sidecar for '{new_source.identifier}' already exists"
            )
        if not old_path.is_file():
            return False
        document = read_annotation_document(vault, old_source)
        document["source_key"] = new_source.key
        document["source"] = new_source.to_payload()
        write_annotation_document(vault, new_source, document)
        old_path.unlink()
        return True
