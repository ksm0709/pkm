"""Tests for source-scoped annotation sidecar storage."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Barrier, Event
from time import sleep

from pkm.annotations.store import (
    AnnotationSource,
    annotation_sidecar_path,
    empty_annotation_document,
    mutate_annotation_document,
    note_lifecycle_lock,
    read_annotation_document,
    write_annotation_document,
)
from pkm.config import VaultConfig


def test_annotation_sidecars_are_split_by_source_kind_and_source_id(
    tmp_vault: VaultConfig,
) -> None:
    data_source = AnnotationSource(kind="data", identifier="report.pdf")
    note_source = AnnotationSource(kind="note", identifier="report.pdf")

    data_path = annotation_sidecar_path(tmp_vault, data_source)
    note_path = annotation_sidecar_path(tmp_vault, note_source)

    assert data_path.parent == tmp_vault.path / ".pkm" / "annotations" / "data"
    assert note_path.parent == tmp_vault.path / ".pkm" / "annotations" / "note"
    assert data_path.name == sha256(b"data:report.pdf").hexdigest() + ".json"
    assert note_path.name == sha256(b"note:report.pdf").hexdigest() + ".json"
    assert data_path != note_path


def test_annotation_document_round_trips_one_json_per_source(
    tmp_vault: VaultConfig,
) -> None:
    source = AnnotationSource(kind="note", identifier="2026-04-01-mvcc")
    document = empty_annotation_document(source)
    document["annotations"].append(
        {
            "id": "ann-1",
            "kind": "note",
            "anchor": {"kind": "text_quote", "quote": "MVCC", "occurrence": 0},
            "comment": "important term",
            "created_at": "2026-07-06T10:00:00Z",
            "updated_at": "2026-07-06T10:00:00Z",
        }
    )

    write_annotation_document(tmp_vault, source, document)
    loaded = read_annotation_document(tmp_vault, source)

    sidecar = annotation_sidecar_path(tmp_vault, source)
    assert loaded == document
    assert sidecar.is_file()
    assert not (tmp_vault.path / ".pkm" / "annotations" / "all.json").exists()


def test_missing_annotation_sidecar_returns_canonical_empty_document(
    tmp_vault: VaultConfig,
) -> None:
    source = AnnotationSource(kind="data", identifier="reports/한글 report.pdf")

    loaded = read_annotation_document(tmp_vault, source)

    assert loaded == {
        "version": 2,
        "source_key": "data:reports/한글 report.pdf",
        "source": {
            "kind": "data",
            "path": "reports/한글 report.pdf",
        },
        "annotations": [],
    }


def test_concurrent_annotation_mutations_preserve_disjoint_updates(
    tmp_vault: VaultConfig,
) -> None:
    source = AnnotationSource(kind="note", identifier="concurrent-note")
    start = Barrier(3)

    def add_annotation(annotation_id: str) -> None:
        start.wait()

        def mutate(document: dict) -> dict:
            sleep(0.05)
            document["annotations"].append({"id": annotation_id})
            return document

        mutate_annotation_document(tmp_vault, source, mutate)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(add_annotation, "first")
        second = executor.submit(add_annotation, "second")
        start.wait()
        first.result(timeout=2)
        second.result(timeout=2)

    loaded = read_annotation_document(tmp_vault, source)
    assert {item["id"] for item in loaded["annotations"]} == {"first", "second"}


def test_note_lifecycle_lock_serializes_note_and_sidecar_mutations(
    tmp_vault: VaultConfig,
) -> None:
    first_entered = Event()
    release_first = Event()
    second_entered = Event()

    def first_mutation() -> None:
        with note_lifecycle_lock(tmp_vault, "locked-note"):
            first_entered.set()
            assert release_first.wait(timeout=2)

    def second_mutation() -> None:
        assert first_entered.wait(timeout=2)
        with note_lifecycle_lock(tmp_vault, "locked-note"):
            second_entered.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(first_mutation)
        second = executor.submit(second_mutation)
        assert first_entered.wait(timeout=2)
        sleep(0.05)
        assert not second_entered.is_set()
        release_first.set()
        first.result(timeout=2)
        second.result(timeout=2)

    assert second_entered.is_set()
