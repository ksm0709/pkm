"""Credential storage helpers for provider API keys."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol

ASK_CREDENTIAL_PROVIDERS: dict[str, str] = {
    "google": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
ASK_CREDENTIAL_LABELS: dict[str, str] = {
    "google": "Google Gemini",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
}
_KEYRING_SERVICE = "pkm"
logger = logging.getLogger(__name__)


class SecretStoreProtocol(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> None: ...


def _validate_secret_value(value: str) -> None:
    if "\n" in value or "\r" in value or "\0" in value:
        raise ValueError("Secret values must be single-line strings")


class FileSecretStore:
    """Simple KEY=value fallback store with private file permissions."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (Path.home() / ".config" / "pkm" / "secrets.env")

    def get(self, key: str) -> str | None:
        return self._read().get(key)

    def set(self, key: str, value: str) -> None:
        _validate_secret_value(value)
        values = self._read()
        values[key] = value
        self._write(values)

    def delete(self, key: str) -> None:
        values = self._read()
        if key in values:
            values.pop(key, None)
            self._write(values)

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        values: dict[str, str] = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key] = value
        return values

    def _write(self, values: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"{key}={value}" for key, value in sorted(values.items())]
        content = ("\n".join(lines) + "\n") if lines else ""
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                fd = -1
                file.write(content)
        finally:
            if fd != -1:
                os.close(fd)


class SecretStore:
    """Keyring-first secret store with file fallback."""

    def __init__(
        self,
        fallback: FileSecretStore | None = None,
        keyring_backend: object | None = None,
    ) -> None:
        self.fallback = fallback or FileSecretStore()
        if keyring_backend is not None:
            self.keyring = keyring_backend
        else:
            try:
                import keyring
            except Exception:
                keyring = None
            self.keyring = keyring

    def get(self, key: str) -> str | None:
        if self.keyring is not None:
            try:
                value = self.keyring.get_password(_KEYRING_SERVICE, key)
                if value:
                    return value
            except Exception:
                logger.warning("Keyring lookup failed for %s; using fallback store", key)
        return self.fallback.get(key)

    def set(self, key: str, value: str) -> None:
        _validate_secret_value(value)
        if self.keyring is not None:
            try:
                self.keyring.set_password(_KEYRING_SERVICE, key, value)
                self.fallback.delete(key)
                return
            except Exception:
                logger.warning("Keyring set failed for %s; using fallback store", key)
        self.fallback.set(key, value)

    def delete(self, key: str) -> None:
        if self.keyring is not None:
            try:
                self.keyring.delete_password(_KEYRING_SERVICE, key)
            except Exception:
                logger.warning(
                    "Keyring delete failed for %s; deleting fallback store value", key
                )
        self.fallback.delete(key)


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return f"{'*' * (len(value) - 4)}{value[-4:]}"


def provider_payload(
    provider: str,
    *,
    store: SecretStoreProtocol | None = None,
) -> dict[str, object]:
    env_key = ASK_CREDENTIAL_PROVIDERS[provider]
    value = (store or SecretStore()).get(env_key) or ""
    return {
        "id": provider,
        "label": ASK_CREDENTIAL_LABELS[provider],
        "env_key": env_key,
        "configured": bool(value),
        "fingerprint": mask_secret(value),
    }


def ask_credential_env(
    *,
    store: SecretStoreProtocol | None = None,
) -> dict[str, str]:
    secret_store = store or SecretStore()
    env: dict[str, str] = {}
    for env_key in ASK_CREDENTIAL_PROVIDERS.values():
        value = secret_store.get(env_key)
        if value:
            env[env_key] = value
    return env
