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
from pkm.credential_store import (
    ASK_CREDENTIAL_PROVIDERS,
    SecretStore,
    agent_credential_env,
    provider_payload,
)
from pkm.models import get_connected_model_options
from pkm.web.routes.notes import _resolve_vault
from pkm.web.security import (
    request_credential_access_allowed,
    request_same_origin_or_bearer_allowed,
)

_GRAPH_SEMANTIC_PREFIX = "graph-semantic-"
_CONFIG_INPUT_TYPES = {
    "graph-depth": "number",
    "model": "select",
    "web-port": "number",
    "web-window-padding": "number",
}
_CONFIG_OPTIONS = {
    "reasoning-effort": ["", "low", "medium", "high"],
}


def _editable_config_schema() -> dict[str, dict[str, Any]]:
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


def _config_section(data: dict[str, Any], key: str) -> dict[str, Any]:
    section = data.get(_section_for_key(key), {})
    return section if isinstance(section, dict) else {}


def _ask_model_options(env: dict[str, str]) -> list[str]:
    return ["auto", *get_connected_model_options(env)]


def _setting_options(key: str, model_options: list[str] | None) -> list[str]:
    if key == "model":
        return model_options or ["auto"]
    return _CONFIG_OPTIONS.get(key, [])


def _setting_payload(
    key: str,
    data: dict[str, Any],
    *,
    model_options: list[str] | None = None,
) -> dict[str, Any]:
    schema = _editable_config_schema()[key]
    internal_key = schema["internal_key"]
    section_name = _section_for_key(key)
    section = _config_section(data, key)
    raw_value = section.get(internal_key)
    value, source = config_value_for_key(key, section, unset_label="")
    options = _setting_options(key, model_options)
    if key == "model" and value and value not in options:
        options = [*options, value]
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
        "options": options,
    }


def _settings_payload(
    data: dict[str, Any],
    *,
    model_options: list[str] | None = None,
) -> list[dict[str, Any]]:
    return [
        _setting_payload(key, data, model_options=model_options)
        for key in sorted(_editable_config_schema().keys())
    ]


async def get_configs(request: web.Request) -> web.Response:
    _resolve_vault(request.match_info["name"])
    data = load_config()
    store = SecretStore()
    model_options = _ask_model_options(agent_credential_env(store=store))
    return web.json_response(
        {
            "settings": _settings_payload(data, model_options=model_options),
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
    store = SecretStore()
    model_options = _ask_model_options(agent_credential_env(store=store))
    return web.json_response(_setting_payload(key, data, model_options=model_options))


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
