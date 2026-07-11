"""Configuration routes for web clients."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from pkm.commands.config import (
    CONFIG_SCHEMA,
    _section_for_key,
    _validate_config_value,
    config_value_for_key,
)
from pkm.config import load_config, save_config
from pkm.web.routes.notes import _resolve_vault
from pkm.web.security import request_same_origin_or_bearer_allowed

_GRAPH_SEMANTIC_PREFIX = "graph-semantic-"
_CONFIG_INPUT_TYPES = {
    "graph-depth": "number",
    "web-port": "number",
    "web-window-padding": "number",
}


def _editable_config_schema() -> dict[str, dict[str, Any]]:
    return {
        key: schema
        for key, schema in CONFIG_SCHEMA.items()
        if not key.startswith(_GRAPH_SEMANTIC_PREFIX)
    }


def _guard_config_write(request: web.Request) -> None:
    if not request_same_origin_or_bearer_allowed(request):
        raise web.HTTPForbidden(reason="Config writes require same-origin or bearer auth")


def _normalise_config_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if not isinstance(value, str):
        raise web.HTTPBadRequest(reason="Config value must be a scalar")
    if "\n" in value or "\r" in value or "\0" in value:
        raise web.HTTPBadRequest(reason="Config value must be a single-line value")
    return value


def _config_section(data: dict[str, Any], key: str) -> dict[str, Any]:
    section = data.get(_section_for_key(key), {})
    return section if isinstance(section, dict) else {}


def _setting_payload(
    key: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    schema = _editable_config_schema()[key]
    internal_key = schema["internal_key"]
    section_name = _section_for_key(key)
    section = _config_section(data, key)
    raw_value = section.get(internal_key)
    value, source = config_value_for_key(key, section, unset_label="")
    return {
        "key": key,
        "section": section_name,
        "internal_key": internal_key,
        "description": schema["description"],
        "value": value,
        "default_value": value if source == "default" else "",
        "configured": raw_value is not None,
        "source": source,
        "input_type": _CONFIG_INPUT_TYPES.get(key, "text"),
        "options": [],
    }


def _settings_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _setting_payload(key, data)
        for key in sorted(_editable_config_schema().keys())
    ]


async def get_configs(request: web.Request) -> web.Response:
    _resolve_vault(request.match_info["name"])
    data = load_config()
    return web.json_response({"settings": _settings_payload(data)})


async def patch_config_setting(request: web.Request) -> web.Response:
    _resolve_vault(request.match_info["name"])
    key = request.match_info["key"]
    schema = _editable_config_schema().get(key)
    if schema is None:
        raise web.HTTPNotFound(reason="Unknown editable config key")
    _guard_config_write(request)

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON body")
    if not isinstance(body, dict) or "value" not in body:
        raise web.HTTPBadRequest(reason="Field 'value' is required")

    value = _normalise_config_value(body["value"])
    data = dict(load_config())
    section_name = _section_for_key(key)
    section = data.get(section_name, {})
    if not isinstance(section, dict):
        section = {}
    section = dict(section)

    internal_key = schema["internal_key"]
    if value in (None, ""):
        section.pop(internal_key, None)
    else:
        try:
            section[internal_key] = _validate_config_value(key, value)
        except Exception as exc:
            raise web.HTTPBadRequest(reason=str(exc))

    data[section_name] = section
    save_config(data)
    return web.json_response(_setting_payload(key, data))
