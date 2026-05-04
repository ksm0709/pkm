"""Tests for daemon worker stdout IPC parsing."""

from __future__ import annotations

import logging

from pkm.daemon import _decode_worker_stdout_line


def test_decode_worker_stdout_line_ignores_non_json_noise(caplog) -> None:
    """Third-party stdout logs must not be treated as daemon IPC failures."""
    caplog.set_level(logging.DEBUG, logger="pkm.daemon")

    assert _decode_worker_stdout_line(b"LiteLLM completion() model=gemini\n") is None
    assert "Ignoring non-JSON worker stdout" in caplog.text


def test_decode_worker_stdout_line_accepts_json_message() -> None:
    assert _decode_worker_stdout_line(b'{"type":"result","id":"t1"}\n') == {
        "type": "result",
        "id": "t1",
    }
