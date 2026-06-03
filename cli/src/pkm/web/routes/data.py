"""Data file REST handlers."""

from __future__ import annotations

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


async def get_data_file(request: web.Request) -> web.StreamResponse:
    """GET a data file under vault data/, including nested relative paths."""
    vault = _resolve_vault(request.match_info["name"])
    relpath = _request_data_path(request)
    target = _data_path(vault, relpath)
    if not target.is_file():
        raise web.HTTPNotFound(reason="Data file not found")

    return web.FileResponse(target, headers=_safe_download_headers(target.name))
