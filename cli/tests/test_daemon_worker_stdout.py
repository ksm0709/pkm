"""Tests for retained daemon keepalive and log redaction helpers."""

from pkm.daemon import _idle_timeout_disabled, redact


def test_redact_removes_nested_secret_material_without_destroying_shape() -> None:
    payload = {
        "api_key": "sk-secret",
        "nested": [
            {"token": "bearer-secret", "value": 3},
            {"name": "public"},
        ],
    }

    assert redact(payload) == {
        "api_key": "<REDACTED>",
        "nested": [
            {"token": "<REDACTED>", "value": 3},
            {"name": "public"},
        ],
    }


def test_keepalive_env_disables_idle_timeout(monkeypatch) -> None:
    monkeypatch.setenv("PKM_DAEMON_KEEPALIVE", "1")
    assert _idle_timeout_disabled() is True


def test_idle_timeout_enabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("PKM_DAEMON_KEEPALIVE", raising=False)
    assert _idle_timeout_disabled() is False
