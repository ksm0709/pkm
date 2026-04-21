"""Tests for tier parameter in get_graph_context and get_graph_context_via_daemon."""

from __future__ import annotations

import inspect
import json
import unittest.mock as mock

import pytest

from pkm.search_engine import get_graph_context_via_daemon
from pkm.tools.search import get_graph_context


def test_tool_default_tier_is_enriched():
    """get_graph_context should default tier to 'enriched'."""
    sig = inspect.signature(get_graph_context)
    assert "tier" in sig.parameters, "get_graph_context must have a 'tier' parameter"
    assert sig.parameters["tier"].default == "enriched"


def test_via_daemon_passes_tier_in_request(tmp_path):
    """get_graph_context_via_daemon should include 'tier' in the socket request."""
    from pkm.config import VaultConfig

    vault_path = tmp_path / "vault"
    (vault_path / ".pkm").mkdir(parents=True)
    graph = vault_path / ".pkm" / "graph_enriched.json"
    graph.write_text("{}", encoding="utf-8")

    vault = VaultConfig(name="test", path=vault_path)

    captured_data = {}

    def fake_socket_context(*args, **kwargs):
        """Return a mock socket that captures the sent request."""
        sock = mock.MagicMock()
        sock.__enter__ = lambda s: s
        sock.__exit__ = mock.MagicMock(return_value=False)

        sent_bytes = []

        def capture_sendall(data):
            sent_bytes.append(data)
            captured_data["request"] = json.loads(data.rstrip(b"\n"))

        sock.sendall = capture_sendall

        resp_line = json.dumps({"nodes": [], "edges": []}) + "\n"
        mock_file = mock.MagicMock()
        mock_file.readline.return_value = resp_line
        sock.makefile.return_value = mock_file

        return sock

    with mock.patch("socket.socket", side_effect=fake_socket_context):
        get_graph_context_via_daemon("some-note", vault, depth=1, tier="enriched")

    assert "request" in captured_data, "No request was sent to the socket"
    assert "tier" in captured_data["request"], (
        "'tier' field missing from request payload"
    )
    assert captured_data["request"]["tier"] == "enriched"


@pytest.mark.parametrize("tier", ["enriched", "structural"])
def test_via_daemon_returns_none_when_no_graph(tmp_path, tier):
    """get_graph_context_via_daemon should return None when neither graph file exists."""
    from pkm.config import VaultConfig

    vault_path = tmp_path / "vault"
    (vault_path / ".pkm").mkdir(parents=True)
    # Do NOT create graph_enriched.json or graph.json

    vault = VaultConfig(name="test", path=vault_path)

    result = get_graph_context_via_daemon("some-note", vault, depth=1, tier=tier)
    assert result is None
