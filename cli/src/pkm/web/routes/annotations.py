"""Unified annotation REST handlers."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from urllib.parse import parse_qs
from aiohttp import web

from pkm.annotations.store import (
    AnnotationSource,
    annotation_document_lock,
    annotation_sidecar_path,
    empty_annotation_document,
    note_lifecycle_lock,
    read_annotation_document,
    write_annotation_document,
)
from pkm.config import VaultConfig
from pkm.frontmatter import parse, render
from pkm.note_lifecycle import (
    find_note_file,
    strip_legacy_annotations_section,
    validate_note_id,
)
from pkm.web.routes.data import (
    _annotation_sidecar_path as _legacy_data_annotation_sidecar_path,
    _data_path,
    _request_data_path,
)
from pkm.web.routes.notes import _note_content_hash, _resolve_vault


def _require_pdf_data_target(vault: VaultConfig, relpath: str) -> None:
    target = _data_path(vault, relpath)
    if not target.is_file():
        raise web.HTTPNotFound(reason="Data file not found")
    if target.suffix.lower() != ".pdf":
        raise web.HTTPUnsupportedMediaType(
            reason="Data annotations require a PDF data file"
        )


def _validated_note_id(note_id: str) -> str:
    try:
        return validate_note_id(note_id)
    except ValueError:
        raise web.HTTPBadRequest(reason="Invalid note id")


def _require_note_target(vault: VaultConfig, note_id: str) -> str:
    try:
        note_path = find_note_file(vault, note_id)
    except ValueError:
        raise web.HTTPBadRequest(reason="Invalid note id")
    if note_path is None:
        raise web.HTTPNotFound(
            reason=f"Note '{note_id}' not found in vault '{vault.name}'"
        )
    return note_id.strip()


def _current_note_revision(vault: VaultConfig, note_id: str) -> str:
    note_path = find_note_file(vault, note_id)
    if note_path is None:
        raise web.HTTPNotFound(reason="Note not found")
    return _note_content_hash(parse(note_path).body)


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
        annotation = dict(raw)
        if source.kind == "note":
            if annotation.get("kind") != "note":
                raise web.HTTPBadRequest(reason="Note annotation kind must be note")
            annotation["anchor"] = _validate_text_quote_anchor(annotation.get("anchor"))
            for field, maximum in (
                ("comment", 100_000),
                ("created_at", 128),
                ("updated_at", 128),
            ):
                value = annotation.get(field)
                if not isinstance(value, str) or len(value) > maximum:
                    raise web.HTTPBadRequest(reason=f"Invalid annotation {field}")
            status = annotation.get("status")
            reanchor = annotation.get("reanchor")
            if (status is None) != (reanchor is None):
                raise web.HTTPBadRequest(
                    reason="Annotation status and reanchor metadata must be paired"
                )
            if status is not None:
                annotation["reanchor"] = _validate_status_reanchor(status, reanchor)
        annotations.append(annotation)

    document = empty_annotation_document(source)
    source_revision = payload.get("source_revision")
    if source_revision is not None:
        if not isinstance(source_revision, str) or not re.fullmatch(
            r"fnv1a:[0-9a-f]{8}", source_revision
        ):
            raise web.HTTPBadRequest(reason="Invalid annotation source revision")
        document["source_revision"] = source_revision
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


def _legacy_revision(payload: dict) -> str:
    encoded = json.dumps(
        payload.get("annotations", []),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _annotation_revision(payload: dict) -> int:
    revision = payload.get("annotation_revision", 0)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise web.HTTPInternalServerError(reason="Invalid annotation revision")
    return revision


def _read_note_annotation_state(
    vault: VaultConfig,
    note_id: str,
    source: AnnotationSource,
) -> tuple[dict, str, str | None]:
    if annotation_sidecar_path(vault, source).is_file():
        return read_annotation_document(vault, source), "v2", None
    legacy = _read_legacy_note_annotations_as_v2(vault, note_id, source)
    if legacy is not None:
        return legacy, "legacy", _legacy_revision(legacy)
    return read_annotation_document(vault, source), "none", None


def _note_annotation_response(
    payload: dict,
    storage_mode: str,
    legacy_revision: str | None = None,
) -> dict:
    response = dict(payload)
    response["annotation_revision"] = _annotation_revision(payload)
    response["storage_mode"] = storage_mode
    if legacy_revision is not None:
        response["legacy_revision"] = legacy_revision
    return response


def _validate_if_match(request: web.Request, raw_payload: dict) -> None:
    if_match = request.headers.get("If-Match")
    if if_match is None:
        return
    base_revision = raw_payload.get("base_revision")
    if (
        isinstance(base_revision, bool)
        or not isinstance(base_revision, int)
        or if_match != f'"{base_revision}"'
    ):
        raise web.HTTPPreconditionFailed(reason="If-Match does not match base_revision")


def _require_base_revision(raw_payload: dict, current: dict) -> int:
    base_revision = raw_payload.get("base_revision")
    if isinstance(base_revision, bool) or not isinstance(base_revision, int):
        raise web.HTTPPreconditionRequired(reason="base_revision is required")
    if base_revision != _annotation_revision(current):
        raise web.HTTPConflict(reason="Annotation document revision changed")
    return base_revision


def _core_text_selector(annotation: dict) -> tuple[object, object, object]:
    anchor = annotation.get("anchor")
    if not isinstance(anchor, dict):
        return None, None, None
    return anchor.get("kind"), anchor.get("quote"), anchor.get("occurrence")


def _merge_compatible_note_put(
    source: AnnotationSource,
    current: dict,
    incoming: dict,
    *,
    preserve_missing: bool,
) -> dict:
    current_by_id = {
        annotation.get("id"): annotation
        for annotation in current.get("annotations", [])
        if isinstance(annotation, dict) and isinstance(annotation.get("id"), str)
    }
    selectors_changed = False
    merged_annotations: list[dict] = []
    for annotation in incoming["annotations"]:
        existing = current_by_id.get(annotation["id"])
        if not isinstance(existing, dict):
            merged_annotations.append(annotation)
            continue
        selector_changed = _core_text_selector(existing) != _core_text_selector(
            annotation
        )
        if selector_changed and not preserve_missing:
            selectors_changed = True
        merged = {**existing, **annotation}
        existing_anchor = existing.get("anchor")
        incoming_anchor = annotation.get("anchor")
        if preserve_missing and selector_changed and isinstance(existing_anchor, dict):
            # A no-CAS compatibility client may be editing a stale projection.
            # Preserve the newer selector rather than rolling back re-anchor data.
            merged["anchor"] = existing_anchor
        elif isinstance(existing_anchor, dict) and isinstance(incoming_anchor, dict):
            merged["anchor"] = {**existing_anchor, **incoming_anchor}
        for field in ("created_at", "updated_at"):
            if annotation.get(field) == "" and existing.get(field):
                merged[field] = existing[field]
        merged_annotations.append(merged)

    if preserve_missing:
        incoming_ids = {annotation["id"] for annotation in incoming["annotations"]}
        merged_annotations.extend(
            annotation
            for annotation in current.get("annotations", [])
            if isinstance(annotation, dict)
            and isinstance(annotation.get("id"), str)
            and annotation["id"] not in incoming_ids
        )

    merged_document = {**incoming, "annotations": merged_annotations}
    if (
        "source_revision" not in incoming
        and not selectors_changed
        and isinstance(current.get("source_revision"), str)
    ):
        merged_document["source_revision"] = current["source_revision"]
    return _canonical_annotation_document(source, merged_document)


async def get_note_annotations(request: web.Request) -> web.Response:
    """GET v2 sidecar annotations for a note or daily note."""

    vault = _resolve_vault(request.match_info["name"])
    note_id = _require_note_target(vault, request.match_info["id"])
    source = AnnotationSource(kind="note", identifier=note_id)
    try:
        payload, storage_mode, legacy_revision = _read_note_annotation_state(
            vault, note_id, source
        )
        response_payload = _note_annotation_response(
            payload, storage_mode, legacy_revision
        )
    except (OSError, json.JSONDecodeError, ValueError):
        raise web.HTTPInternalServerError(reason="Failed to read annotations")
    revision = response_payload["annotation_revision"]
    return web.json_response(response_payload, headers={"ETag": f'"{revision}"'})


def _validate_text_quote_anchor(anchor: object) -> dict:
    if not isinstance(anchor, dict) or anchor.get("kind") != "text_quote":
        raise web.HTTPBadRequest(reason="Re-anchor requires text_quote anchor")
    quote = anchor.get("quote")
    occurrence = anchor.get("occurrence")
    if not isinstance(quote, str) or not quote.strip() or len(quote) > 10_000:
        raise web.HTTPBadRequest(reason="Text quote must be a bounded non-empty string")
    if (
        isinstance(occurrence, bool)
        or not isinstance(occurrence, int)
        or occurrence < 0
    ):
        raise web.HTTPBadRequest(reason="Text quote occurrence must be non-negative")
    selector_version = anchor.get("selector_version")
    if selector_version is not None and selector_version != 1:
        raise web.HTTPBadRequest(reason="Unsupported text selector version")
    for field in ("prefix", "suffix"):
        value = anchor.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > 512):
            raise web.HTTPBadRequest(reason=f"Invalid text selector {field}")
    start = anchor.get("start")
    end = anchor.get("end")
    if (start is None) != (end is None):
        raise web.HTTPBadRequest(reason="Text selector offsets must be paired")
    if start is not None:
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end < start
            or end - start != len(quote.encode("utf-16-le")) // 2
        ):
            raise web.HTTPBadRequest(reason="Invalid text selector range")
    heading_path = anchor.get("heading_path")
    if heading_path is not None and (
        not isinstance(heading_path, list)
        or len(heading_path) > 16
        or any(not isinstance(item, str) or len(item) > 256 for item in heading_path)
    ):
        raise web.HTTPBadRequest(reason="Invalid text selector heading path")
    return dict(anchor)


def _validate_reanchor_metadata(metadata: object) -> dict:
    if not isinstance(metadata, dict):
        raise web.HTTPBadRequest(reason="Re-anchor update requires metadata")
    confidence = metadata.get("confidence")
    reason = metadata.get("reason")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        raise web.HTTPBadRequest(reason="Invalid re-anchor confidence")
    if reason not in {"exact", "context", "ambiguous", "missing"}:
        raise web.HTTPBadRequest(reason="Invalid re-anchor reason")
    return dict(metadata)


def _validate_status_reanchor(status: object, metadata: object) -> dict:
    reanchor = _validate_reanchor_metadata(metadata)
    confidence = reanchor["confidence"]
    reason = reanchor["reason"]
    valid = (
        (status == "active" and reason in {"exact", "context"} and confidence > 0)
        or (status == "needs_review" and reason == "ambiguous" and confidence == 0)
        or (status == "orphaned" and reason == "missing" and confidence == 0)
    )
    if not valid:
        raise web.HTTPBadRequest(
            reason="Annotation status contradicts re-anchor metadata"
        )
    return reanchor


async def patch_note_annotation_anchors(request: web.Request) -> web.Response:
    """Merge automatic re-anchor results without replacing sibling annotations."""

    vault = _resolve_vault(request.match_info["name"])
    note_id = _validated_note_id(request.match_info["id"])
    try:
        raw_payload = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Expected JSON re-anchor patch")
    if not isinstance(raw_payload, dict):
        raise web.HTTPBadRequest(reason="Re-anchor patch must be an object")
    _validate_if_match(request, raw_payload)
    source_revision = raw_payload.get("source_revision")
    base_note_revision = raw_payload.get("base_note_revision")
    updates = raw_payload.get("updates")
    if not isinstance(source_revision, str) or not re.fullmatch(
        r"fnv1a:[0-9a-f]{8}", source_revision
    ):
        raise web.HTTPBadRequest(reason="Invalid annotation source revision")
    if not isinstance(base_note_revision, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", base_note_revision
    ):
        raise web.HTTPPreconditionRequired(reason="base_note_revision is required")
    if not isinstance(updates, list):
        raise web.HTTPBadRequest(reason="Re-anchor patch requires updates list")
    if len(updates) > 10_000:
        raise web.HTTPRequestEntityTooLarge(max_size=10_000, actual_size=len(updates))

    validated_updates: list[tuple[str, dict, str, dict]] = []
    seen_ids: set[str] = set()
    for update in updates:
        if not isinstance(update, dict):
            raise web.HTTPBadRequest(reason="Re-anchor update must be an object")
        annotation_id = update.get("id")
        if not isinstance(annotation_id, str) or not annotation_id:
            raise web.HTTPBadRequest(reason="Re-anchor update requires annotation id")
        if annotation_id in seen_ids:
            raise web.HTTPBadRequest(reason="Duplicate re-anchor annotation id")
        seen_ids.add(annotation_id)
        anchor = _validate_text_quote_anchor(update.get("anchor"))
        status = update.get("status")
        if not isinstance(status, str):
            raise web.HTTPBadRequest(reason="Invalid annotation status")
        reanchor = _validate_status_reanchor(status, update.get("reanchor"))
        validated_updates.append((annotation_id, anchor, status, reanchor))

    source = AnnotationSource(kind="note", identifier=note_id)
    try:
        with note_lifecycle_lock(vault, note_id):
            _require_note_target(vault, note_id)
            with annotation_document_lock(vault, source):
                payload, storage_mode, _legacy = _read_note_annotation_state(
                    vault, note_id, source
                )
                if storage_mode == "legacy":
                    raise web.HTTPConflict(
                        reason="Legacy annotations require explicit sidecar migration"
                    )
                _require_base_revision(raw_payload, payload)
                if _current_note_revision(vault, note_id) != base_note_revision:
                    raise web.HTTPConflict(
                        reason="Note content changed before re-anchor patch"
                    )
                annotations = payload.get("annotations")
                if not isinstance(annotations, list):
                    raise web.HTTPInternalServerError(
                        reason="Invalid annotation document"
                    )
                annotations_by_id = {
                    annotation.get("id"): annotation
                    for annotation in annotations
                    if isinstance(annotation, dict)
                    and isinstance(annotation.get("id"), str)
                }
                for annotation_id, anchor, status, reanchor in validated_updates:
                    if annotation_id not in annotations_by_id:
                        raise web.HTTPConflict(
                            reason="Annotation changed before re-anchor patch"
                        )
                    annotation = annotations_by_id[annotation_id]
                    annotation["anchor"] = anchor
                    annotation["status"] = status
                    annotation["reanchor"] = reanchor
                payload["source_revision"] = source_revision
                payload["annotation_revision"] = _annotation_revision(payload) + 1
                write_annotation_document(vault, source, payload)
    except (OSError, json.JSONDecodeError):
        raise web.HTTPInternalServerError(reason="Failed to update annotations")

    response_payload = _note_annotation_response(payload, "v2")
    revision = response_payload["annotation_revision"]
    return web.json_response(response_payload, headers={"ETag": f'"{revision}"'})


async def put_note_annotations(request: web.Request) -> web.Response:
    """Replace or compatibly merge v2 sidecar annotations for a note."""

    vault = _resolve_vault(request.match_info["name"])
    note_id = _validated_note_id(request.match_info["id"])
    try:
        raw_payload = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Expected JSON annotation document")
    source = AnnotationSource(kind="note", identifier=note_id)
    if isinstance(raw_payload, dict):
        _validate_if_match(request, raw_payload)
    incoming = _canonical_annotation_document(source, raw_payload)
    has_base_revision = isinstance(raw_payload, dict) and "base_revision" in raw_payload

    try:
        with note_lifecycle_lock(vault, note_id):
            _require_note_target(vault, note_id)
            with annotation_document_lock(vault, source):
                current, storage_mode, legacy_revision = _read_note_annotation_state(
                    vault, note_id, source
                )
                if has_base_revision:
                    _require_base_revision(raw_payload, current)
                if storage_mode == "legacy":
                    supplied_legacy_revision = (
                        raw_payload.get("legacy_revision")
                        if isinstance(raw_payload, dict)
                        else None
                    )
                    if supplied_legacy_revision != legacy_revision:
                        raise web.HTTPConflict(
                            reason=(
                                "Legacy annotation source changed or migration not "
                                "acknowledged"
                            )
                        )
                incoming = _merge_compatible_note_put(
                    source,
                    current,
                    incoming,
                    preserve_missing=not has_base_revision,
                )
                incoming["annotation_revision"] = _annotation_revision(current) + 1
                write_annotation_document(vault, source, incoming)

                if storage_mode == "legacy":
                    note_path = find_note_file(vault, note_id)
                    if note_path is None:
                        annotation_sidecar_path(vault, source).unlink(missing_ok=True)
                        raise web.HTTPNotFound(reason=f"Note '{note_id}' not found")
                    note = parse(note_path)
                    stripped_body = strip_legacy_annotations_section(note.body)
                    try:
                        note_path.write_text(
                            render(dict(note.meta or {}), stripped_body),
                            encoding="utf-8",
                        )
                    except OSError:
                        annotation_sidecar_path(vault, source).unlink(missing_ok=True)
                        raise
    except (OSError, json.JSONDecodeError):
        raise web.HTTPInternalServerError(reason="Failed to update annotations")

    response_payload = _note_annotation_response(incoming, "v2")
    revision = response_payload["annotation_revision"]
    return web.json_response(response_payload, headers={"ETag": f'"{revision}"'})
