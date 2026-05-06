"""Configuration routes for web clients."""

from __future__ import annotations

from aiohttp import web

from pkm.credential_store import ASK_CREDENTIAL_PROVIDERS, SecretStore, provider_payload
from pkm.web.routes.notes import _resolve_vault
from pkm.web.security import request_credential_access_allowed


def _provider_or_404(provider: str) -> str:
    if provider not in ASK_CREDENTIAL_PROVIDERS:
        raise web.HTTPNotFound(reason="Unknown credential provider")
    return ASK_CREDENTIAL_PROVIDERS[provider]


def _guard_credential_access(request: web.Request) -> None:
    if not request_credential_access_allowed(request):
        raise web.HTTPForbidden(reason="Credential access is not allowed")


async def get_configs(request: web.Request) -> web.Response:
    _resolve_vault(request.match_info["name"])
    store = SecretStore()
    return web.json_response(
        {
            "ask_credentials": {
                "providers": [
                    provider_payload(provider, store=store)
                    for provider in ASK_CREDENTIAL_PROVIDERS
                ]
            }
        }
    )


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
