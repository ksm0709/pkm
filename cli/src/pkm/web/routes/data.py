"""Data file REST handlers."""

from __future__ import annotations

import json
import math
import os
import tempfile
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote

from aiohttp import hdrs, web

from pkm.config import VaultConfig
from pkm.web.routes.notes import _resolve_vault

_SAFE_INLINE_CONTENT_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}
_RENDERABLE_VIEWER_SUFFIXES = {".htm", ".html", ".markdown", ".md", ".pdf"}


def _sanitize_filename(raw_name: str | None) -> str:
    """Return a flat filename that cannot escape vault data/."""
    name = (raw_name or "").strip()
    if not name:
        raise web.HTTPBadRequest(reason="Uploaded file must include a filename")
    if "/" in name or "\\" in name:
        raise web.HTTPBadRequest(reason="Filename must not include path separators")

    basename = Path(name).name
    if basename != name or basename in {"", ".", ".."}:
        raise web.HTTPBadRequest(reason="Invalid filename")
    return basename


def _sanitize_data_relpath(raw_path: str | None) -> str:
    """Return a relative vault data/ path that cannot escape data/."""
    path = (raw_path or "").strip()
    if not path:
        raise web.HTTPBadRequest(reason="Data file path is required")
    if "\\" in path:
        raise web.HTTPBadRequest(reason="Data file path must use forward slashes")

    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise web.HTTPBadRequest(reason="Invalid data file path")

    candidate = Path(path)
    if candidate.is_absolute():
        raise web.HTTPBadRequest(reason="Data file path must be relative")
    return "/".join(parts)


def _request_data_path(request: web.Request) -> str:
    return _sanitize_data_relpath(
        request.match_info.get("path") or request.match_info.get("filename")
    )


def _data_path(vault: VaultConfig, filename: str) -> Path:
    data_root = vault.data_dir.resolve()
    target = (data_root / filename).resolve()
    try:
        target.relative_to(data_root)
    except ValueError:
        raise web.HTTPBadRequest(reason="Invalid data file path")
    return target


def _candidate_paths(vault: VaultConfig, filename: str):
    target = _data_path(vault, filename)
    yield target

    stem = target.stem
    suffix = target.suffix
    for index in range(1, 10_000):
        yield _data_path(vault, f"{stem}-{index}{suffix}")


def _data_href(vault_name: str, filename: str) -> str:
    return (
        f"/api/v1/vault/{quote(vault_name, safe='')}/data/"
        f"{quote(filename, safe='')}"
    )


def _escape_markdown_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _upload_markdown(filename: str, href: str, content_type: str) -> str:
    label = _escape_markdown_label(filename)
    media_type = content_type.lower().split(";", 1)[0]
    if media_type in _SAFE_INLINE_CONTENT_TYPES:
        return f"![{label}]({href})"
    return f"[{label}]({href})"


def _safe_download_headers(filename: str) -> dict[str, str]:
    content_type = "application/octet-stream"
    media_type = {
        ".gif": "image/gif",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(Path(filename).suffix.lower())

    headers = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }
    if media_type in _SAFE_INLINE_CONTENT_TYPES:
        headers[hdrs.CONTENT_TYPE] = media_type
        return headers

    fallback_name = filename.replace("\\", "_").replace('"', "_")
    encoded_name = quote(filename, safe="")
    headers[hdrs.CONTENT_TYPE] = content_type
    headers[hdrs.CONTENT_DISPOSITION] = (
        f'attachment; filename="{fallback_name}"; filename*=UTF-8\'\'{encoded_name}'
    )
    return headers


async def post_data_file(request: web.Request) -> web.Response:
    """POST /api/v1/vault/{name}/data — upload one file into vault data/."""
    vault_name = request.match_info["name"]
    vault = _resolve_vault(vault_name)

    try:
        reader = await request.multipart()
    except Exception:
        raise web.HTTPBadRequest(reason="Expected multipart/form-data")

    field = None
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "file":
            field = part
            break
        await part.release()

    if field is None:
        raise web.HTTPBadRequest(reason="Multipart field 'file' is required")

    filename = _sanitize_filename(field.filename)
    content_type = field.headers.get(hdrs.CONTENT_TYPE, "application/octet-stream")
    vault.data_dir.mkdir(parents=True, exist_ok=True)

    target = None
    handle = None
    for candidate in _candidate_paths(vault, filename):
        try:
            handle = candidate.open("xb")
            target = candidate
            break
        except FileExistsError:
            continue
    if target is None or handle is None:
        raise web.HTTPConflict(reason="No available filename")

    size = 0
    try:
        with handle:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                size += len(chunk)
                handle.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise

    href = _data_href(vault_name, target.name)
    return web.json_response(
        {
            "filename": target.name,
            "href": href,
            "markdown": _upload_markdown(target.name, href, content_type),
            "size": size,
            "content_type": content_type,
        },
        status=201,
    )


def _viewer_href(vault_name: str, relpath: str) -> str:
    return f"/{quote(vault_name, safe='')}/view-data/{quote(relpath, safe='/')}"


def _is_renderable_viewer_path(path: str) -> bool:
    return Path(path).suffix.lower() in _RENDERABLE_VIEWER_SUFFIXES


async def get_data_file(request: web.Request) -> web.StreamResponse:
    """GET a data file under vault data/, including nested relative paths."""
    vault = _resolve_vault(request.match_info["name"])
    relpath = _request_data_path(request)
    target = _data_path(vault, relpath)
    if not target.is_file():
        raise web.HTTPNotFound(reason="Data file not found")

    return web.FileResponse(target, headers=_safe_download_headers(target.name))


async def get_human_data_file(request: web.Request) -> web.StreamResponse:
    """Browser-openable data links redirect renderable text files to the SPA viewer."""
    vault_name = request.match_info["name"]
    vault = _resolve_vault(vault_name)
    relpath = _request_data_path(request)
    target = _data_path(vault, relpath)
    if not target.is_file():
        raise web.HTTPNotFound(reason="Data file not found")

    if _is_renderable_viewer_path(relpath):
        raise web.HTTPSeeOther(location=_viewer_href(vault_name, relpath))

    return web.FileResponse(target, headers=_safe_download_headers(target.name))


def _annotation_document(relpath: str, annotations: list[dict]) -> dict:
    return {"version": 1, "source_path": relpath, "annotations": annotations}


def _annotation_sidecar_path(vault: VaultConfig, relpath: str) -> Path:
    root = (vault.path / ".pkm" / "data-annotations").resolve()
    digest = sha256(relpath.encode("utf-8")).hexdigest()
    target = (root / f"{digest}.json").resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise web.HTTPBadRequest(reason="Invalid annotation sidecar path")
    return target


def _require_pdf_data_target(vault: VaultConfig, relpath: str) -> Path:
    target = _data_path(vault, relpath)
    if not target.is_file():
        raise web.HTTPNotFound(reason="Data file not found")
    if target.suffix.lower() != ".pdf":
        raise web.HTTPUnsupportedMediaType(reason="PDF annotations require a PDF data file")
    return target


def _as_finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise web.HTTPBadRequest(reason=f"Annotation rect {field} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise web.HTTPBadRequest(reason=f"Annotation rect {field} must be finite")
    return number


def _as_positive_page(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise web.HTTPBadRequest(reason="Annotation rect page must be a positive integer")
    return value


def _validate_rect(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise web.HTTPBadRequest(reason="Annotation rect must be an object")
    page = _as_positive_page(raw.get("page"))
    x = _as_finite_number(raw.get("x"), "x")
    y = _as_finite_number(raw.get("y"), "y")
    width = _as_finite_number(raw.get("width"), "width")
    height = _as_finite_number(raw.get("height"), "height")
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise web.HTTPBadRequest(reason="Annotation rect must have positive in-bounds area")
    if x > 1 or y > 1 or width > 1 or height > 1 or x + width > 1 or y + height > 1:
        raise web.HTTPBadRequest(reason="Annotation rect must be normalized to page bounds")
    return {"page": page, "x": x, "y": y, "width": width, "height": height}


def _optional_string(raw: dict, field: str) -> str:
    value = raw.get(field, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise web.HTTPBadRequest(reason=f"Annotation {field} must be a string")
    return value


def _validate_annotation_payload(payload: object, relpath: str) -> dict:
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

        annotation_type = raw.get("type")
        if annotation_type not in {"area", "text"}:
            raise web.HTTPBadRequest(reason="Annotation type must be area or text")
        rects = raw.get("rects")
        if not isinstance(rects, list) or not rects:
            raise web.HTTPBadRequest(reason="Annotation rects must be a non-empty list")

        annotation = {
            "id": annotation_id,
            "type": annotation_type,
            "rects": [_validate_rect(rect) for rect in rects],
            "comment": _optional_string(raw, "comment"),
            "created_at": _optional_string(raw, "created_at"),
            "updated_at": _optional_string(raw, "updated_at"),
        }
        quote_value = _optional_string(raw, "quote")
        if annotation_type == "text" and not quote_value:
            raise web.HTTPBadRequest(reason="Text annotations require quote")
        if quote_value:
            annotation["quote"] = quote_value
        annotations.append(annotation)

    return _annotation_document(relpath, annotations)


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = None
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
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)


async def get_pdf_annotations(request: web.Request) -> web.Response:
    """GET sidecar annotations for a PDF data file."""
    vault = _resolve_vault(request.match_info["name"])
    relpath = _request_data_path(request)
    _require_pdf_data_target(vault, relpath)
    sidecar = _annotation_sidecar_path(vault, relpath)
    if not sidecar.is_file():
        return web.json_response(_annotation_document(relpath, []))
    try:
        with sidecar.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        raise web.HTTPInternalServerError(reason="Failed to read PDF annotations")
    return web.json_response(payload)


async def put_pdf_annotations(request: web.Request) -> web.Response:
    """Replace sidecar annotations for a PDF data file."""
    vault = _resolve_vault(request.match_info["name"])
    relpath = _request_data_path(request)
    _require_pdf_data_target(vault, relpath)
    try:
        raw_payload = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Expected JSON annotation document")
    payload = _validate_annotation_payload(raw_payload, relpath)
    sidecar = _annotation_sidecar_path(vault, relpath)
    _write_json_atomic(sidecar, payload)
    return web.json_response(payload)
