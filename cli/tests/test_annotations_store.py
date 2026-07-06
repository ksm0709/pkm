"""Tests for source-scoped annotation sidecar storage."""

from __future__ import annotations

from hashlib import sha256

from pkm.annotations.store import (
    AnnotationSource,
    annotation_sidecar_path,
    empty_annotation_document,
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
