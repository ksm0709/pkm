from __future__ import annotations

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
def config_store(monkeypatch) -> dict:
    data = {
        "defaults": {
            "vault": "test-vault",
            "graph-depth": "2",
            "graph-semantic-score-threshold": "0.7",
        }
    }

    def fake_save_config(updated: dict) -> None:
        data.clear()
        data.update(updated)

    monkeypatch.setattr(configs_route, "load_config", lambda: data)
    monkeypatch.setattr(configs_route, "save_config", fake_save_config)
    return data


@pytest.fixture
def app(web_cfg: WebConfig, config_store: dict):
    return make_app(web_config=web_cfg)


@pytest.mark.anyio
async def test_get_configs_returns_editable_pkm_settings_except_graph_semantic(
    app, tmp_vault: VaultConfig
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/configs",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        body = await resp.json()

    assert resp.status == 200
    assert "ask_credentials" not in body
    settings = {setting["key"]: setting for setting in body["settings"]}
    assert settings["default-vault"]["value"] == "test-vault"
    assert settings["default-vault"]["source"] == "configured"
    assert settings["graph-depth"]["input_type"] == "number"
    assert settings["web-port"]["section"] == "web"
    assert settings["web-port"]["value"] == "7420"
    assert settings["web-port"]["input_type"] == "number"
    assert settings["web-window-padding"]["section"] == "web"
    assert settings["web-window-padding"]["value"] == "32"
    assert settings["web-window-padding"]["default_value"] == "32"
    assert settings["web-window-padding"]["input_type"] == "number"
    assert settings["editor"]["configured"] is False
    assert settings["editor"]["source"] == "default"
    assert settings["editor"]["value"]
    assert "model" not in settings
    assert "reasoning-effort" not in settings
    assert "graph-semantic-score-threshold" not in settings
    assert all(not key.startswith("graph-semantic-") for key in settings)


@pytest.mark.anyio
async def test_patch_config_setting_updates_defaults(
    app, tmp_vault: VaultConfig, config_store: dict
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/configs/settings/graph-depth",
            json={"value": 4},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        body = await resp.json()

    assert resp.status == 200
    assert body["key"] == "graph-depth"
    assert body["value"] == "4"
    assert config_store["defaults"]["graph-depth"] == "4"
    assert config_store["defaults"]["graph-semantic-score-threshold"] == "0.7"


@pytest.mark.anyio
async def test_patch_web_port_updates_web_section(
    app, tmp_vault: VaultConfig, config_store: dict
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/configs/settings/web-port",
            json={"value": 8123},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        body = await resp.json()

    assert resp.status == 200
    assert body["key"] == "web-port"
    assert body["section"] == "web"
    assert body["value"] == "8123"
    assert config_store["web"]["port"] == "8123"


@pytest.mark.anyio
async def test_patch_web_port_rejects_invalid_value(
    app, tmp_vault: VaultConfig, config_store: dict
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/configs/settings/web-port",
            json={"value": "70000"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert resp.status == 400
    assert "web-port must be an integer" in resp.reason
    assert "web" not in config_store


@pytest.mark.anyio
async def test_patch_web_window_padding_updates_web_section(
    app, tmp_vault: VaultConfig, config_store: dict
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/configs/settings/web-window-padding",
            json={"value": 96},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        body = await resp.json()

    assert resp.status == 200
    assert body["key"] == "web-window-padding"
    assert body["section"] == "web"
    assert body["value"] == "96"
    assert config_store["web"]["window_padding"] == "96"


@pytest.mark.anyio
async def test_patch_web_window_padding_rejects_invalid_value(
    app, tmp_vault: VaultConfig, config_store: dict
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/configs/settings/web-window-padding",
            json={"value": "1.5"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert resp.status == 400
    assert "web-window-padding must be an integer" in resp.reason
    assert "web" not in config_store


@pytest.mark.anyio
async def test_patch_config_setting_clears_empty_value(
    app, tmp_vault: VaultConfig, config_store: dict
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/configs/settings/graph-depth",
            json={"value": ""},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        body = await resp.json()

    assert resp.status == 200
    assert body["configured"] is False
    assert body["source"] == "default"
    assert body["value"] == "0"
    assert "graph-depth" not in config_store["defaults"]


@pytest.mark.anyio
async def test_patch_config_setting_rejects_graph_semantic_key(
    app, tmp_vault: VaultConfig, config_store: dict
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.patch(
            "/api/v1/vault/test-vault/configs/settings/graph-semantic-score-threshold",
            json={"value": "0.9"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert resp.status == 404
    assert config_store["defaults"]["graph-semantic-score-threshold"] == "0.7"


@pytest.mark.anyio
async def test_patch_config_setting_rejects_no_origin_without_bearer(
    app, tmp_vault: VaultConfig, config_store: dict
) -> None:
    async with TestClient(TestServer(app)) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"password": "correct horse"},
        )
        assert login.status == 200

        resp = await client.patch(
            "/api/v1/vault/test-vault/configs/settings/graph-depth",
            json={"value": "6"},
        )

    assert resp.status == 403
    assert config_store["defaults"]["graph-depth"] == "2"
