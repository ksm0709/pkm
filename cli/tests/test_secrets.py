from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from pkm.credential_store import (
    ASK_CREDENTIAL_PROVIDERS,
    FileSecretStore,
    SecretStore,
    agent_credential_env,
    ask_credential_env,
    mask_secret,
    provider_payload,
)


def test_file_secret_store_writes_single_line_values_with_private_mode(tmp_path: Path) -> None:
    path = tmp_path / "secrets.env"
    store = FileSecretStore(path)

    store.set("GEMINI_API_KEY", "gemini-secret")

    assert store.get("GEMINI_API_KEY") == "gemini-secret"
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.read_text(encoding="utf-8") == "GEMINI_API_KEY=gemini-secret\n"


def test_file_secret_store_creates_file_private_from_open(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "secrets.env"
    opened_modes: list[int] = []
    real_open = os.open

    def recording_open(file, flags, mode=0o777, *args, **kwargs):
        opened_modes.append(mode)
        return real_open(file, flags, mode, *args, **kwargs)

    monkeypatch.setattr(os, "open", recording_open)

    FileSecretStore(path).set("GEMINI_API_KEY", "gemini-secret")

    assert opened_modes == [0o600]
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("value", ["two\nlines", "carriage\rreturn", "nul\0byte"])
def test_file_secret_store_rejects_multiline_values(tmp_path: Path, value: str) -> None:
    store = FileSecretStore(tmp_path / "secrets.env")

    with pytest.raises(ValueError):
        store.set("OPENAI_API_KEY", value)


def test_file_secret_store_deletes_value_without_losing_other_keys(tmp_path: Path) -> None:
    store = FileSecretStore(tmp_path / "secrets.env")
    store.set("GEMINI_API_KEY", "gemini-secret")
    store.set("OPENAI_API_KEY", "openai-secret")

    store.delete("GEMINI_API_KEY")

    assert store.get("GEMINI_API_KEY") is None
    assert store.get("OPENAI_API_KEY") == "openai-secret"


def test_secret_store_uses_keyring_first_and_deletes_stale_fallback(tmp_path: Path) -> None:
    fallback = FileSecretStore(tmp_path / "secrets.env")
    fallback.set("ANTHROPIC_API_KEY", "stale")
    keyring = _FakeKeyring()
    store = SecretStore(fallback=fallback, keyring_backend=keyring)

    store.set("ANTHROPIC_API_KEY", "fresh")

    assert keyring.values[("pkm", "ANTHROPIC_API_KEY")] == "fresh"
    assert fallback.get("ANTHROPIC_API_KEY") is None
    assert store.get("ANTHROPIC_API_KEY") == "fresh"


def test_secret_store_falls_back_to_file_when_keyring_unavailable(tmp_path: Path) -> None:
    fallback = FileSecretStore(tmp_path / "secrets.env")
    store = SecretStore(fallback=fallback, keyring_backend=_UnavailableKeyring())

    store.set("OPENAI_API_KEY", "file-secret")

    assert fallback.get("OPENAI_API_KEY") == "file-secret"
    assert store.get("OPENAI_API_KEY") == "file-secret"


def test_secret_store_logs_keyring_fallback_without_secret(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fallback = FileSecretStore(tmp_path / "secrets.env")
    store = SecretStore(fallback=fallback, keyring_backend=_UnavailableKeyring())

    with caplog.at_level(logging.WARNING, logger="pkm.credential_store"):
        store.set("OPENAI_API_KEY", "do-not-log-this")

    assert fallback.get("OPENAI_API_KEY") == "do-not-log-this"
    assert "keyring" in caplog.text.lower()
    assert "OPENAI_API_KEY" in caplog.text
    assert "do-not-log-this" not in caplog.text


def test_secret_store_logs_keyring_delete_failure_without_secret(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fallback = FileSecretStore(tmp_path / "secrets.env")
    fallback.set("OPENAI_API_KEY", "file-secret")
    store = SecretStore(fallback=fallback, keyring_backend=_UnavailableKeyring())

    with caplog.at_level(logging.WARNING, logger="pkm.credential_store"):
        store.delete("OPENAI_API_KEY")

    assert fallback.get("OPENAI_API_KEY") is None
    assert "keyring" in caplog.text.lower()
    assert "OPENAI_API_KEY" in caplog.text
    assert "file-secret" not in caplog.text


def test_secret_store_delete_removes_keyring_and_fallback(tmp_path: Path) -> None:
    fallback = FileSecretStore(tmp_path / "secrets.env")
    fallback.set("OPENAI_API_KEY", "file-secret")
    keyring = _FakeKeyring()
    keyring.set_password("pkm", "OPENAI_API_KEY", "ring-secret")
    store = SecretStore(fallback=fallback, keyring_backend=keyring)

    store.delete("OPENAI_API_KEY")

    assert fallback.get("OPENAI_API_KEY") is None
    assert keyring.values == {}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", ""),
        ("abcd", "****"),
        ("abcde", "*bcde"),
        ("super-secret", "********cret"),
    ],
)
def test_mask_secret(value: str, expected: str) -> None:
    assert mask_secret(value) == expected


def test_provider_payload_and_ask_credential_env() -> None:
    store = _MemoryStore({"GEMINI_API_KEY": "gemini-secret"})

    assert ASK_CREDENTIAL_PROVIDERS["google"] == "GEMINI_API_KEY"
    assert provider_payload("google", store=store) == {
        "id": "google",
        "label": "Google Gemini",
        "env_key": "GEMINI_API_KEY",
        "configured": True,
        "fingerprint": "*********cret",
    }
    assert provider_payload("openai", store=store)["configured"] is False
    assert ask_credential_env(store=store) == {"GEMINI_API_KEY": "gemini-secret"}


def test_agent_credential_env_combines_process_and_saved_credentials() -> None:
    store = _MemoryStore({"OPENAI_API_KEY": "saved-openai"})

    assert agent_credential_env(
        store=store,
        process_env={
            "OPENAI_API_KEY": "process-openai",
            "CUSTOM_API_KEY": "custom-secret",
            "NOT_A_SECRET": "ignored",
        },
    ) == {
        "OPENAI_API_KEY": "saved-openai",
        "CUSTOM_API_KEY": "custom-secret",
    }


class _MemoryStore:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def get(self, key: str) -> str | None:
        return self.values.get(key)


class _FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


class _UnavailableKeyring(_FakeKeyring):
    def get_password(self, service: str, username: str) -> str | None:
        raise RuntimeError("no keyring")

    def set_password(self, service: str, username: str, password: str) -> None:
        raise RuntimeError("no keyring")

    def delete_password(self, service: str, username: str) -> None:
        raise RuntimeError("no keyring")
