"""Configuration routes for web clients."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from pkm.commands.config import CONFIG_SCHEMA
from pkm.config import load_config, save_config
from pkm.credential_store import ASK_CREDENTIAL_PROVIDERS, SecretStore, provider_payload
from pkm.web.routes.notes import _resolve_vault
from pkm.web.security import (
    request_credential_access_allowed,
    request_same_origin_or_bearer_allowed,
)

_GRAPH_SEMANTIC_PREFIX = "graph-semantic-"
_CONFIG_INPUT_TYPES = {
    "auto": "boolean",
    "graph-depth": "number",
}
_CONFIG_OPTIONS = {
    "reasoning-effort": ["", "low", "medium", "high"],
}


def _editable_config_schema() -> dict[str, dict[str, str]]:
    return {
        key: schema
        for key, schema in CONFIG_SCHEMA.items()
        if not key.startswith(_GRAPH_SEMANTIC_PREFIX)
    }


def _provider_or_404(provider: str) -> str:
    if provider not in ASK_CREDENTIAL_PROVIDERS:
        raise web.HTTPNotFound(reason="Unknown credential provider")
    return ASK_CREDENTIAL_PROVIDERS[provider]


def _guard_credential_access(request: web.Request) -> None:
    if not request_credential_access_allowed(request):
        raise web.HTTPForbidden(reason="Credential access is not allowed")


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


def _setting_payload(key: str, defaults: dict[str, Any]) -> dict[str, Any]:
    schema = _editable_config_schema()[key]
    internal_key = schema["internal_key"]
    raw_value = defaults.get(internal_key)
    return {
        "key": key,
        "section": "defaults",
        "internal_key": internal_key,
        "description": schema["description"],
        "value": "" if raw_value is None else str(raw_value),
        "configured": raw_value is not None,
        "input_type": _CONFIG_INPUT_TYPES.get(key, "text"),
        "options": _CONFIG_OPTIONS.get(key, []),
    }


def _settings_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}
    return [
        _setting_payload(key, defaults)
        for key in sorted(_editable_config_schema().keys())
    ]


async def get_configs(request: web.Request) -> web.Response:
    _resolve_vault(request.match_info["name"])
    data = load_config()
    store = SecretStore()
    return web.json_response(
        {
            "settings": _settings_payload(data),
            "ask_credentials": {
                "providers": [
                    provider_payload(provider, store=store)
                    for provider in ASK_CREDENTIAL_PROVIDERS
                ]
            }
        }
    )


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
    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}
    defaults = dict(defaults)

    internal_key = schema["internal_key"]
    if value in (None, ""):
        defaults.pop(internal_key, None)
    else:
        defaults[internal_key] = value

    data["defaults"] = defaults
    save_config(data)
    return web.json_response(_setting_payload(key, defaults))


async def put_ask_credential(request: web.Request) -> web.Response:
    _resolve_vault(request.match_info["name"])
    provider = request.match_info["provider"]
    env_key = _provider_or_404(provider)
    _guard_credential_access(request)

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON body")

    api_key = body.get("api_key") if isinstance(body, dict) else None
    if not isinstance(api_key, str) or not api_key:
        raise web.HTTPBadRequest(reason="Field 'api_key' is required")
    if "\n" in api_key or "\r" in api_key or "\0" in api_key:
        raise web.HTTPBadRequest(reason="API key must be a single-line value")

    store = SecretStore()
    try:
        store.set(env_key, api_key)
    except ValueError as exc:
        raise web.HTTPBadRequest(reason=str(exc))

    return web.json_response(provider_payload(provider, store=store))


async def delete_ask_credential(request: web.Request) -> web.Response:
    _resolve_vault(request.match_info["name"])
    provider = request.match_info["provider"]
    env_key = _provider_or_404(provider)
    _guard_credential_access(request)

    store = SecretStore()
    store.delete(env_key)
    return web.json_response(provider_payload(provider, store=store))
