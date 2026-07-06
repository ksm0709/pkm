"""Unified annotation REST handlers."""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs
from aiohttp import web

from pkm.annotations.store import (
    AnnotationSource,
    annotation_sidecar_path,
    empty_annotation_document,
    read_annotation_document,
    write_annotation_document,
)
from pkm.config import VaultConfig
from pkm.note_lifecycle import find_note_file
from pkm.web.routes.data import (
    _annotation_sidecar_path as _legacy_data_annotation_sidecar_path,
    _data_path,
    _request_data_path,
)
from pkm.web.routes.notes import _resolve_vault


def _require_pdf_data_target(vault: VaultConfig, relpath: str) -> None:
    target = _data_path(vault, relpath)
    if not target.is_file():
        raise web.HTTPNotFound(reason="Data file not found")
    if target.suffix.lower() != ".pdf":
        raise web.HTTPUnsupportedMediaType(reason="Data annotations require a PDF data file")


def _require_note_target(vault: VaultConfig, note_id: str) -> str:
    try:
        note_path = find_note_file(vault, note_id)
    except ValueError:
        raise web.HTTPBadRequest(reason="Invalid note id")
    if note_path is None:
        raise web.HTTPNotFound(reason=f"Note '{note_id}' not found in vault '{vault.name}'")
    return note_id.strip()


def _canonical_annotation_document(source: AnnotationSource, payload: object) -> dict:
    if not isinstance(payload, dict):
        raise web.HTTPBadRequest(reason="Annotation document must be an object")
    raw_annotations = payload.get("annotations")
    if not isinstance(raw_annotations, list):
        raise web.HTTPBadRequest(reason="Annotation document requires annotations list")

    annotations: list[dict] = []
    seen_ids: set[str] = set()
    for raw in raw_annotations:
        if not isinstance(raw, dict):
            raise web.HTTPBadRequest(reason="Annotation must be an object")
        annotation_id = raw.get("id")
        if not isinstance(annotation_id, str) or not annotation_id.strip():
            raise web.HTTPBadRequest(reason="Annotation id must be a non-empty string")
        if annotation_id in seen_ids:
            raise web.HTTPBadRequest(reason="Annotation ids must be unique")
        seen_ids.add(annotation_id)
        annotations.append(dict(raw))

    document = empty_annotation_document(source)
    document["annotations"] = annotations
    return document


def _legacy_pdf_annotation_to_v2(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("legacy annotation must be an object")
    annotation_type = raw.get("type")
    rects = raw.get("rects")
    if annotation_type not in {"area", "text"} or not isinstance(rects, list):
        raise ValueError("legacy annotation has invalid PDF shape")

    annotation = {
        "id": raw.get("id"),
        "kind": annotation_type,
        "anchor": {
            "kind": "pdf_text" if annotation_type == "text" else "pdf_rects",
            "rects": rects,
        },
        "comment": raw.get("comment", ""),
        "created_at": raw.get("created_at", ""),
        "updated_at": raw.get("updated_at", ""),
    }
    quote = raw.get("quote")
    if annotation_type == "text" and quote:
        annotation["anchor"]["quote"] = quote
    return annotation


def _read_legacy_data_annotations_as_v2(
    vault: VaultConfig,
    relpath: str,
    source: AnnotationSource,
) -> dict | None:
    legacy_path = _legacy_data_annotation_sidecar_path(vault, relpath)
    if not legacy_path.is_file():
        return None
    with legacy_path.open("r", encoding="utf-8") as handle:
        legacy_payload = json.load(handle)
    raw_annotations = legacy_payload.get("annotations")
    if not isinstance(raw_annotations, list):
        raise ValueError("legacy annotation document requires annotations list")
    document = empty_annotation_document(source)
    document["annotations"] = [
        _legacy_pdf_annotation_to_v2(annotation) for annotation in raw_annotations
    ]
    return document


def _annotation_memo_line(line: str) -> str:
    list_item = re.match(r"^\s+-\s?(?P<text>.*)$", line)
    if list_item:
        return list_item.group("text").rstrip()
    continuation = re.match(r"^\s{4,}(?P<text>.*)$", line)
    return continuation.group("text").rstrip() if continuation else ""


def _parse_annotation_source_hash(href: str) -> tuple[str, int] | None:
    raw = href[1:] if href.startswith("#") else href
    params = parse_qs(raw, keep_blank_values=True)
    quote = (params.get("quote") or [""])[0].strip()
    if not quote:
        return None
    try:
        occurrence = max(0, int((params.get("occ") or ["0"])[0]))
    except ValueError:
        occurrence = 0
    return quote, occurrence


def _read_legacy_note_annotations_as_v2(
    vault: VaultConfig,
    note_id: str,
    source: AnnotationSource,
) -> dict | None:
    note_path = find_note_file(vault, note_id)
    if note_path is None:
        return None
    body = note_path.read_text(encoding="utf-8")
    lines = re.split(r"\r?\n", body)
    heading_index = next(
        (index for index, line in enumerate(lines) if line.strip() == "## Annotations"),
        -1,
    )
    if heading_index < 0:
        return None

    annotations: list[dict] = []
    current: dict | None = None

    def flush(end_line: int) -> None:
        nonlocal current
        if current is None:
            return
        comment = "\n".join(current["memo_lines"]).strip()
        if comment:
            source_href = current["source_href"]
            annotations.append(
                {
                    "id": f"{source_href}\u0000{current['index']}",
                    "kind": "note",
                    "anchor": {
                        "kind": "text_quote",
                        "quote": current["quote"],
                        "occurrence": current["occurrence"],
                    },
                    "comment": comment,
                    "created_at": "",
                    "updated_at": "",
                }
            )
        current = None

    for index in range(heading_index + 1, len(lines)):
        line = lines[index]
        if re.match(r"^#{1,6}\s+", line):
            flush(index)
            break
        entry = re.match(
            r"^-\s+[“\"]?(?P<quote>.*?)[”\"]?\s*\(\[↩ 원문\]\((?P<href>#[^)]+)\)\)\s*$",
            line,
        )
        if entry:
            flush(index)
            parsed = _parse_annotation_source_hash(entry.group("href"))
            if parsed is None:
                current = None
                continue
            quote, occurrence = parsed
            current = {
                "quote": quote or entry.group("quote").strip(),
                "occurrence": occurrence,
                "source_href": entry.group("href"),
                "memo_lines": [],
                "index": index,
            }
            continue
        if current is None:
            continue
        if re.match(r"^-\s+", line):
            flush(index)
            continue
        if not line.strip():
            current["memo_lines"].append("")
            continue
        current["memo_lines"].append(_annotation_memo_line(line))
    else:
        flush(len(lines))

    document = empty_annotation_document(source)
    document["annotations"] = annotations
    return document


async def get_data_annotations(request: web.Request) -> web.Response:
    """GET v2 sidecar annotations for a PDF data file."""

    vault = _resolve_vault(request.match_info["name"])
    relpath = _request_data_path(request)
    _require_pdf_data_target(vault, relpath)
    source = AnnotationSource(kind="data", identifier=relpath)
    try:
        if annotation_sidecar_path(vault, source).is_file():
            payload = read_annotation_document(vault, source)
        else:
            payload = _read_legacy_data_annotations_as_v2(vault, relpath, source)
            if payload is None:
                payload = read_annotation_document(vault, source)
    except (OSError, json.JSONDecodeError, ValueError):
        raise web.HTTPInternalServerError(reason="Failed to read annotations")
    return web.json_response(payload)


async def put_data_annotations(request: web.Request) -> web.Response:
    """Replace v2 sidecar annotations for a PDF data file."""

    vault = _resolve_vault(request.match_info["name"])
    relpath = _request_data_path(request)
    _require_pdf_data_target(vault, relpath)
    try:
        raw_payload = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Expected JSON annotation document")
    source = AnnotationSource(kind="data", identifier=relpath)
    payload = _canonical_annotation_document(source, raw_payload)
    write_annotation_document(vault, source, payload)
    return web.json_response(payload)


async def get_note_annotations(request: web.Request) -> web.Response:
    """GET v2 sidecar annotations for a note or daily note."""

    vault = _resolve_vault(request.match_info["name"])
    note_id = _require_note_target(vault, request.match_info["id"])
    source = AnnotationSource(kind="note", identifier=note_id)
    try:
        if annotation_sidecar_path(vault, source).is_file():
            payload = read_annotation_document(vault, source)
        else:
            payload = _read_legacy_note_annotations_as_v2(vault, note_id, source)
            if payload is None:
                payload = read_annotation_document(vault, source)
    except (OSError, json.JSONDecodeError):
        raise web.HTTPInternalServerError(reason="Failed to read annotations")
    return web.json_response(payload)


async def put_note_annotations(request: web.Request) -> web.Response:
    """Replace v2 sidecar annotations for a note or daily note."""

    vault = _resolve_vault(request.match_info["name"])
    note_id = _require_note_target(vault, request.match_info["id"])
    try:
        raw_payload = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Expected JSON annotation document")
    source = AnnotationSource(kind="note", identifier=note_id)
    payload = _canonical_annotation_document(source, raw_payload)
    write_annotation_document(vault, source, payload)
    return web.json_response(payload)
