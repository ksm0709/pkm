"""Request/network guards for sensitive web operations."""

from __future__ import annotations

import hmac
from aiohttp import web


def request_same_origin_or_bearer_allowed(request: web.Request) -> bool:
    origin = request.headers.get("Origin")
    if origin is not None:
        expected = f"{request.scheme}://{request.host}"
        return hmac.compare_digest(origin.rstrip("/"), expected.rstrip("/"))

    auth_header = request.headers.get("Authorization", "")
    return auth_header.startswith("Bearer ")
