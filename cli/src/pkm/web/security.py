"""Request/network guards for sensitive web operations."""

from __future__ import annotations

import hmac
import ipaddress

from aiohttp import web


def credential_remote_allowed(remote: str | None) -> bool:
    if not remote:
        return False
    try:
        ip = ipaddress.ip_address(remote)
    except ValueError:
        return False
    return (
        ip.is_loopback
        or ip in ipaddress.ip_network("100.64.0.0/10")
        or ip in ipaddress.ip_network("fd7a:115c:a1e0::/48")
    )


def request_remote_allowed(request: web.Request) -> bool:
    return credential_remote_allowed(request.remote)


def request_same_origin_or_bearer_allowed(request: web.Request) -> bool:
    origin = request.headers.get("Origin")
    if origin is not None:
        expected = f"{request.scheme}://{request.host}"
        return hmac.compare_digest(origin.rstrip("/"), expected.rstrip("/"))

    auth_header = request.headers.get("Authorization", "")
    return auth_header.startswith("Bearer ")


def request_credential_access_allowed(request: web.Request) -> bool:
    return request_remote_allowed(request) and request_same_origin_or_bearer_allowed(
        request
    )
