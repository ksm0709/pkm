"""Scenario tests for shared web config-write security gates."""

from __future__ import annotations

from types import SimpleNamespace

from pkm.web.security import request_same_origin_or_bearer_allowed


def _request(
    *,
    headers: dict[str, str] | None = None,
    scheme: str = "http",
    host: str = "localhost:7444",
):
    return SimpleNamespace(
        headers=headers or {},
        scheme=scheme,
        host=host,
    )


def test_origin_header_takes_precedence_over_bearer_fallback() -> None:
    """A present Origin must match the request host; bearer is only no-Origin fallback."""
    assert request_same_origin_or_bearer_allowed(
        _request(headers={"Origin": "http://localhost:7444/"})
    )
    assert not request_same_origin_or_bearer_allowed(
        _request(
            headers={
                "Origin": "https://evil.example",
                "Authorization": "Bearer token",
            }
        )
    )
    assert request_same_origin_or_bearer_allowed(
        _request(headers={"Authorization": "Bearer token"})
    )
    assert not request_same_origin_or_bearer_allowed(
        _request(headers={"Authorization": "Basic token"})
    )
