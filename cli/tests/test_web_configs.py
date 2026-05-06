from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import VaultConfig, WebConfig
from pkm.web.auth import hash_password
from pkm.web.routes import configs as configs_route
from pkm.web.server import make_app

TOKEN = "test-configs-token"


@pytest.fixture
def web_cfg(tmp_path: Path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    password_path = tmp_path / "web-password"
    password_path.write_text(hash_password("correct horse"), encoding="utf-8")
    return WebConfig(
        port=7434,
        bind="127.0.0.1",
        token_path=token_path,
        password_path=password_path,
    )


@pytest.fixture
def secret_store(monkeypatch) -> "_MemorySecretStore":
    store = _MemorySecretStore()
    monkeypatch.setattr(configs_route, "SecretStore", lambda: store)
    return store


@pytest.fixture
def app(web_cfg: WebConfig, secret_store: "_MemorySecretStore"):
    return make_app(web_config=web_cfg)


@pytest.mark.anyio
async def test_get_configs_returns_provider_metadata_without_raw_secrets(
    app, tmp_vault: VaultConfig, secret_store: "_MemorySecretStore"
) -> None:
    secret_store.values["GEMINI_API_KEY"] = "gemini-secret"

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/configs",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        body = await resp.json()

    assert resp.status == 200
    providers = body["ask_credentials"]["providers"]
    assert isinstance(providers, list)
    assert providers[0] == {
        "id": "google",
        "label": "Google Gemini",
        "env_key": "GEMINI_API_KEY",
        "configured": True,
        "fingerprint": "*********cret",
    }
    assert [provider["id"] for provider in providers] == ["google", "openai", "anthropic"]
    assert "gemini-secret" not in str(body)


@pytest.mark.anyio
async def test_put_ask_credential_saves_key_for_allowed_remote(
    app, tmp_vault: VaultConfig, secret_store: "_MemorySecretStore"
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.put(
            "/api/v1/vault/test-vault/configs/ask/credentials/openai",
            json={"api_key": "openai-secret"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        body = await resp.json()

    assert resp.status == 200
    assert secret_store.values == {"OPENAI_API_KEY": "openai-secret"}
    assert body == {
        "id": "openai",
        "label": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "configured": True,
        "fingerprint": "*********cret",
    }


@pytest.mark.anyio
async def test_put_ask_credential_rejects_browser_csrf_from_untrusted_origin(
    app, tmp_vault: VaultConfig, secret_store: "_MemorySecretStore"
) -> None:
    async with TestClient(TestServer(app)) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"password": "correct horse"},
        )
        assert login.status == 200

        resp = await client.put(
            "/api/v1/vault/test-vault/configs/ask/credentials/google",
            json={"api_key": "gemini-secret"},
            headers={"Origin": "https://evil.example"},
        )

    assert resp.status == 403
    assert secret_store.values == {}


@pytest.mark.anyio
async def test_put_ask_credential_rejects_cross_origin_even_with_bearer(
    app, tmp_vault: VaultConfig, secret_store: "_MemorySecretStore"
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.put(
            "/api/v1/vault/test-vault/configs/ask/credentials/google",
            json={"api_key": "gemini-secret"},
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Origin": "https://evil.example",
            },
        )

    assert resp.status == 403
    assert secret_store.values == {}


@pytest.mark.anyio
async def test_put_ask_credential_rejects_no_origin_without_bearer(
    app, tmp_vault: VaultConfig, secret_store: "_MemorySecretStore"
) -> None:
    async with TestClient(TestServer(app)) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"password": "correct horse"},
        )
        assert login.status == 200

        resp = await client.put(
            "/api/v1/vault/test-vault/configs/ask/credentials/google",
            json={"api_key": "gemini-secret"},
        )

    assert resp.status == 403
    assert secret_store.values == {}


@pytest.mark.anyio
async def test_put_ask_credential_allows_no_origin_with_bearer(
    app, tmp_vault: VaultConfig, secret_store: "_MemorySecretStore"
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.put(
            "/api/v1/vault/test-vault/configs/ask/credentials/google",
            json={"api_key": "gemini-secret"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert resp.status == 200
    assert secret_store.values == {"GEMINI_API_KEY": "gemini-secret"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"api_key": ""},
        {"api_key": "bad\nkey"},
        {"api_key": "bad\rkey"},
        {"api_key": "bad\0key"},
    ],
)
async def test_put_ask_credential_rejects_invalid_payload(
    app, tmp_vault: VaultConfig, secret_store: "_MemorySecretStore", payload: dict
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.put(
            "/api/v1/vault/test-vault/configs/ask/credentials/google",
            json=payload,
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert resp.status == 400
    assert secret_store.values == {}


@pytest.mark.anyio
async def test_put_ask_credential_rejects_invalid_json(
    app, tmp_vault: VaultConfig, secret_store: "_MemorySecretStore"
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.put(
            "/api/v1/vault/test-vault/configs/ask/credentials/google",
            data="{not-json",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
        )

    assert resp.status == 400
    assert secret_store.values == {}


@pytest.mark.anyio
async def test_put_ask_credential_unknown_provider_returns_404(
    app, tmp_vault: VaultConfig
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.put(
            "/api/v1/vault/test-vault/configs/ask/credentials/unknown",
            json={"api_key": "secret"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert resp.status == 404


@pytest.mark.anyio
async def test_delete_ask_credential_removes_key(
    app, tmp_vault: VaultConfig, secret_store: "_MemorySecretStore"
) -> None:
    secret_store.values["ANTHROPIC_API_KEY"] = "anthropic-secret"

    async with TestClient(TestServer(app)) as client:
        resp = await client.delete(
            "/api/v1/vault/test-vault/configs/ask/credentials/anthropic",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        body = await resp.json()

    assert resp.status == 200
    assert secret_store.values == {}
    assert body == {
        "id": "anthropic",
        "label": "Anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "configured": False,
        "fingerprint": "",
    }


@dataclass
class _MemorySecretStore:
    values: dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)
