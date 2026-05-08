"""Scenario tests for web credential access security gates."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pkm.web.security import (
    credential_remote_allowed,
    request_credential_access_allowed,
    request_same_origin_or_bearer_allowed,
)


def _request(
    *,
    remote: str | None = "127.0.0.1",
    headers: dict[str, str] | None = None,
    scheme: str = "http",
    host: str = "localhost:7444",
):
    return SimpleNamespace(
        remote=remote,
        headers=headers or {},
        scheme=scheme,
        host=host,
    )


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("100.64.0.1", True),
        ("100.127.255.254", True),
        ("fd7a:115c:a1e0::1", True),
        (None, False),
        ("", False),
        ("localhost", False),
        ("203.0.113.9", False),
        ("100.128.0.1", False),
    ],
)
def test_credential_remote_policy_allows_only_local_or_tailscale_addresses(
    remote: str | None, expected: bool
) -> None:
    """Credential routes are reachable only from local/Tailscale network origins."""
    assert credential_remote_allowed(remote) is expected


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


@pytest.mark.parametrize(
    ("fake_request", "expected"),
    [
        (_request(headers={"Origin": "http://localhost:7444"}), True),
        (
            _request(remote="203.0.113.9", headers={"Origin": "http://localhost:7444"}),
            False,
        ),
        (_request(headers={"Origin": "https://evil.example"}), False),
        (_request(headers={"Authorization": "Bearer token"}), True),
    ],
)
def test_credential_access_requires_allowed_remote_and_origin_or_bearer(
    fake_request, expected: bool
) -> None:
    """Credential access is granted only when network and request-auth gates both pass."""
    assert request_credential_access_allowed(fake_request) is expected
