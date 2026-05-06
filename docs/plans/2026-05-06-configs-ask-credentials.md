# Configs Ask Credentials Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add a vault-scoped Configs page where a local single user can safely enter, test, delete, and use Ask model API keys without storing secrets in the browser.

**Architecture:** The browser renders a reusable `/{vault}/configs` settings hub and only sends API keys once over authenticated same-origin requests. The daemon stores secrets in an OS keyring when available, falls back to a `0600` local secrets file, returns only status/fingerprint metadata to the UI, and injects saved keys into Ask worker tasks server-side.

**Tech Stack:** SvelteKit/Svelte 5 frontend, aiohttp backend, optional Python `keyring`, local permission-restricted fallback file, existing Playwright/Vitest/pytest test suites.

---

### Task 1: Add Secret Storage Abstraction Tests

**Objective:** Define the storage contract before adding implementation.

**Files:**
- Create: `cli/tests/test_secrets.py`
- Create: `cli/src/pkm/secrets.py`

**Step 1: Write failing tests**

```python
# cli/tests/test_secrets.py
from pathlib import Path

from pkm.secrets import (
    ASK_CREDENTIAL_PROVIDERS,
    FileSecretStore,
    mask_secret,
)


def test_mask_secret_never_returns_full_value():
    assert mask_secret("") == ""
    assert mask_secret("abcd") == "****"
    assert mask_secret("sk-test-1234567890") == "************7890"


def test_file_secret_store_writes_0600_and_reads_status(tmp_path: Path):
    store = FileSecretStore(tmp_path / "secrets.env")
    store.set("OPENAI_API_KEY", "sk-test-secret")

    assert oct((tmp_path / "secrets.env").stat().st_mode & 0o777) == "0o600"
    assert store.get("OPENAI_API_KEY") == "sk-test-secret"
    assert store.status("OPENAI_API_KEY") == {
        "configured": True,
        "fingerprint": "**********cret",
    }


def test_provider_registry_uses_litellm_environment_names():
    assert ASK_CREDENTIAL_PROVIDERS["google"]["env_key"] == "GEMINI_API_KEY"
    assert ASK_CREDENTIAL_PROVIDERS["openai"]["env_key"] == "OPENAI_API_KEY"
    assert ASK_CREDENTIAL_PROVIDERS["anthropic"]["env_key"] == "ANTHROPIC_API_KEY"
```

**Step 2: Run test to verify failure**

Run: `uv run --project cli --extra web --extra search pytest cli/tests/test_secrets.py -q`

Expected: FAIL because `pkm.secrets` does not exist.

**Step 3: Commit**

Do not commit yet. Commit after Task 2 when the tests pass.

---

### Task 2: Implement Secret Storage

**Objective:** Provide keyring-first storage with a deterministic file fallback.

**Files:**
- Modify: `cli/pyproject.toml`
- Create: `cli/src/pkm/secrets.py`
- Test: `cli/tests/test_secrets.py`

**Step 1: Add optional dependency**

Modify `cli/pyproject.toml`:

```toml
[project.optional-dependencies]
web = [
    "aiohttp>=3.9",
    "keyring>=25.0",
]
```

Keep existing optional extras intact; only add `keyring` to `web`.

**Step 2: Add implementation**

```python
# cli/src/pkm/secrets.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SECRET_PATH = Path.home() / ".config" / "pkm" / "secrets.env"
KEYRING_SERVICE = "pkm.ask"

ASK_CREDENTIAL_PROVIDERS = {
    "google": {"label": "Google Gemini", "env_key": "GEMINI_API_KEY"},
    "openai": {"label": "OpenAI", "env_key": "OPENAI_API_KEY"},
    "anthropic": {"label": "Anthropic", "env_key": "ANTHROPIC_API_KEY"},
}


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return "*" * (len(value) - 4) + value[-4:]


@dataclass
class FileSecretStore:
    path: Path = SECRET_PATH

    def get(self, env_key: str) -> str | None:
        for line in self._read_lines():
            key, sep, value = line.partition("=")
            if sep and key == env_key:
                return value
        return None

    def set(self, env_key: str, value: str) -> None:
        values = {
            key: current
            for key, current in (
                line.partition("=")[::2] for line in self._read_lines() if "=" in line
            )
        }
        values[env_key] = value
        self._write(values)

    def delete(self, env_key: str) -> None:
        values = {
            key: current
            for key, current in (
                line.partition("=")[::2] for line in self._read_lines() if "=" in line
            )
            if key != env_key
        }
        self._write(values)

    def status(self, env_key: str) -> dict[str, object]:
        value = self.get(env_key) or ""
        return {"configured": bool(value), "fingerprint": mask_secret(value)}

    def _read_lines(self) -> list[str]:
        if not self.path.exists():
            return []
        return self.path.read_text(encoding="utf-8").splitlines()

    def _write(self, values: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for key, value in sorted(values.items()):
                f.write(f"{key}={value}\n")
        os.chmod(self.path, 0o600)


class SecretStore:
    def __init__(self, fallback: FileSecretStore | None = None):
        self.fallback = fallback or FileSecretStore()

    def get(self, env_key: str) -> str | None:
        value = self._keyring_get(env_key)
        return value if value else self.fallback.get(env_key)

    def set(self, env_key: str, value: str) -> None:
        if not self._keyring_set(env_key, value):
            self.fallback.set(env_key, value)

    def delete(self, env_key: str) -> None:
        self._keyring_delete(env_key)
        self.fallback.delete(env_key)

    def status(self, env_key: str) -> dict[str, object]:
        value = self.get(env_key) or ""
        return {"configured": bool(value), "fingerprint": mask_secret(value)}

    def _keyring_get(self, env_key: str) -> str | None:
        try:
            import keyring

            return keyring.get_password(KEYRING_SERVICE, env_key)
        except Exception:
            return None

    def _keyring_set(self, env_key: str, value: str) -> bool:
        try:
            import keyring

            keyring.set_password(KEYRING_SERVICE, env_key, value)
            return True
        except Exception:
            return False

    def _keyring_delete(self, env_key: str) -> None:
        try:
            import keyring

            keyring.delete_password(KEYRING_SERVICE, env_key)
        except Exception:
            return


def provider_payload(provider_id: str, store: SecretStore | None = None) -> dict[str, object]:
    provider = ASK_CREDENTIAL_PROVIDERS[provider_id]
    status = (store or SecretStore()).status(provider["env_key"])
    return {
        "id": provider_id,
        "label": provider["label"],
        "env_key": provider["env_key"],
        **status,
    }


def ask_credential_env(store: SecretStore | None = None) -> dict[str, str]:
    active_store = store or SecretStore()
    result: dict[str, str] = {}
    for provider in ASK_CREDENTIAL_PROVIDERS.values():
        env_key = provider["env_key"]
        value = active_store.get(env_key)
        if value:
            result[env_key] = value
    return result
```

**Step 3: Run tests**

Run: `uv run --project cli --extra web --extra search pytest cli/tests/test_secrets.py -q`

Expected: PASS.

**Step 4: Commit**

```bash
git add cli/pyproject.toml cli/src/pkm/secrets.py cli/tests/test_secrets.py
git commit -m "Add local Ask credential secret storage"
```

Use the repo Lore trailer format in the commit body.

---

### Task 3: Add Configs API Tests

**Objective:** Specify server endpoints for settings-page credential status, save, delete, and test.

**Files:**
- Create: `cli/tests/test_web_configs.py`
- Create: `cli/src/pkm/web/routes/configs.py`
- Modify: `cli/src/pkm/web/routes/__init__.py`

**Step 1: Write failing API tests**

```python
# cli/tests/test_web_configs.py
import pytest
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import VaultConfig, WebConfig
from pkm.web.server import make_app

TOKEN = "test-token"


@pytest.fixture
def tmp_vault(tmp_path, monkeypatch):
    vault = tmp_path / "vaults" / "test-vault"
    (vault / "notes").mkdir(parents=True)
    vc = VaultConfig(name="test-vault", path=vault)
    monkeypatch.setattr("pkm.web.routes.notes.discover_vaults", lambda: {"test-vault": vc})
    monkeypatch.setattr("pkm.config.discover_vaults", lambda root=None: {"test-vault": vc})
    return vc


@pytest.fixture
def app(tmp_path, tmp_vault):
    token = tmp_path / "token"
    token.write_text(TOKEN)
    return make_app(web_config=WebConfig(port=0, bind="127.0.0.1", token_path=token))


@pytest.mark.anyio
async def test_configs_status_never_returns_secret_values(app, tmp_vault, monkeypatch):
    class FakeStore:
        def status(self, env_key):
            return {"configured": env_key == "OPENAI_API_KEY", "fingerprint": "********1234"}

    monkeypatch.setattr("pkm.web.routes.configs.SecretStore", lambda: FakeStore())

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/configs",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        body = await resp.json()

    assert resp.status == 200
    assert "sk-" not in str(body)
    assert body["ask_credentials"]["providers"][1]["id"] == "openai"
    assert body["ask_credentials"]["providers"][1]["configured"] is True


@pytest.mark.anyio
async def test_save_and_delete_credential(app, tmp_vault, monkeypatch):
    calls = []

    class FakeStore:
        def set(self, env_key, value):
            calls.append(("set", env_key, value))

        def delete(self, env_key):
            calls.append(("delete", env_key))

    monkeypatch.setattr("pkm.web.routes.configs.SecretStore", lambda: FakeStore())

    async with TestClient(TestServer(app)) as client:
        save = await client.put(
            "/api/v1/vault/test-vault/configs/ask/credentials/openai",
            json={"api_key": "sk-test-secret"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        delete = await client.delete(
            "/api/v1/vault/test-vault/configs/ask/credentials/openai",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert save.status == 200
    assert delete.status == 200
    assert calls == [
        ("set", "OPENAI_API_KEY", "sk-test-secret"),
        ("delete", "OPENAI_API_KEY"),
    ]
```

**Step 2: Run test to verify failure**

Run: `uv run --project cli --extra web --extra search pytest cli/tests/test_web_configs.py -q`

Expected: FAIL because route module is missing.

---

### Task 4: Implement Configs API Routes

**Objective:** Add authenticated backend routes that never return secret values.

**Files:**
- Create: `cli/src/pkm/web/routes/configs.py`
- Modify: `cli/src/pkm/web/routes/__init__.py`
- Test: `cli/tests/test_web_configs.py`

**Step 1: Add route implementation**

```python
# cli/src/pkm/web/routes/configs.py
from __future__ import annotations

from typing import Any

from aiohttp import web

from pkm.secrets import ASK_CREDENTIAL_PROVIDERS, SecretStore, provider_payload
from pkm.web.routes.notes import _resolve_vault


def _provider_or_404(provider_id: str) -> dict[str, str]:
    provider = ASK_CREDENTIAL_PROVIDERS.get(provider_id)
    if provider is None:
        raise web.HTTPNotFound(reason="Unknown credential provider")
    return provider


async def get_configs(request: web.Request) -> web.Response:
    _resolve_vault(request.match_info["name"])
    store = SecretStore()
    providers = [
        provider_payload(provider_id, store)
        for provider_id in ASK_CREDENTIAL_PROVIDERS.keys()
    ]
    return web.json_response({"ask_credentials": {"providers": providers}})


async def put_ask_credential(request: web.Request) -> web.Response:
    _resolve_vault(request.match_info["name"])
    provider = _provider_or_404(request.match_info["provider"])
    body: dict[str, Any] = await request.json()
    api_key = str(body.get("api_key") or "").strip()
    if not api_key:
        raise web.HTTPBadRequest(reason="api_key is required")
    SecretStore().set(provider["env_key"], api_key)
    return web.json_response({"ok": True, "provider": request.match_info["provider"]})


async def delete_ask_credential(request: web.Request) -> web.Response:
    _resolve_vault(request.match_info["name"])
    provider = _provider_or_404(request.match_info["provider"])
    SecretStore().delete(provider["env_key"])
    return web.json_response({"ok": True, "provider": request.match_info["provider"]})


async def test_ask_credential(request: web.Request) -> web.Response:
    _resolve_vault(request.match_info["name"])
    provider = _provider_or_404(request.match_info["provider"])
    value = SecretStore().get(provider["env_key"])
    if not value:
        return web.json_response({"ok": False, "message": "API key is not configured"}, status=400)
    return web.json_response({"ok": True})
```

**Step 2: Register routes**

Modify `cli/src/pkm/web/routes/__init__.py`:

```python
from pkm.web.routes.configs import (
    delete_ask_credential,
    get_configs,
    put_ask_credential,
    test_ask_credential,
)

# In register_routes, after vault or before ask:
app.router.add_get("/api/v1/vault/{name}/configs", get_configs)
app.router.add_put(
    "/api/v1/vault/{name}/configs/ask/credentials/{provider}",
    put_ask_credential,
)
app.router.add_delete(
    "/api/v1/vault/{name}/configs/ask/credentials/{provider}",
    delete_ask_credential,
)
app.router.add_post(
    "/api/v1/vault/{name}/configs/ask/credentials/{provider}/test",
    test_ask_credential,
)
```

**Step 3: Run tests**

Run: `uv run --project cli --extra web --extra search pytest cli/tests/test_web_configs.py -q`

Expected: PASS.

**Step 4: Commit**

```bash
git add cli/src/pkm/web/routes/configs.py cli/src/pkm/web/routes/__init__.py cli/tests/test_web_configs.py
git commit -m "Expose Configs API for Ask credentials"
```

Use the repo Lore trailer format in the commit body.

---

### Task 5: Inject Saved Credentials Into Ask Runs

**Objective:** Make saved credentials affect actual Ask model resolution without exposing them to the browser.

**Files:**
- Modify: `cli/src/pkm/web/routes/ask.py`
- Modify: `cli/tests/test_web_ask_sse.py`

**Step 1: Write failing test**

Append to `cli/tests/test_web_ask_sse.py`:

```python
@pytest.mark.anyio
async def test_ask_injects_saved_credentials_server_side(
    app, tmp_vault: VaultConfig, patch_daemon, monkeypatch
) -> None:
    fake = _FakeWorker()
    monkeypatch.setattr(_daemon, "worker_proxy", fake)
    monkeypatch.setattr(
        ask_route,
        "ask_credential_env",
        lambda: {"OPENAI_API_KEY": "sk-server-side"},
    )

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/ask",
            json={"query": "anything", "env_keys": {"OPENAI_API_KEY": "browser-value"}},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        await resp.text()

    assert resp.status == 200
    assert fake.tasks_seen[-1]["env_keys"] == {"OPENAI_API_KEY": "sk-server-side"}
```

**Step 2: Run test to verify failure**

Run: `uv run --project cli --extra web --extra search pytest cli/tests/test_web_ask_sse.py -k "injects_saved_credentials" -q`

Expected: FAIL because `ask_credential_env` is not used by `post_ask`.

**Step 3: Implement**

Modify `cli/src/pkm/web/routes/ask.py`:

```python
from pkm.secrets import ask_credential_env

# In task payload:
"env_keys": ask_credential_env(),
```

Do not merge `body.get("env_keys")` into the HTTP Ask path. Browser-supplied environment variables should not override daemon-owned credential storage.

**Step 4: Run tests**

Run:

```bash
uv run --project cli --extra web --extra search pytest cli/tests/test_web_ask_sse.py -k "injects_saved_credentials or default_model" -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add cli/src/pkm/web/routes/ask.py cli/tests/test_web_ask_sse.py
git commit -m "Use saved Ask credentials for web Ask runs"
```

Use the repo Lore trailer format in the commit body.

---

### Task 6: Add Configs Page Navigation Tests

**Objective:** Make Configs a first-class app page and CmdK destination.

**Files:**
- Modify: `web-frontend/tests/playwright/cmdk-shell.spec.ts`
- Modify: `web-frontend/tests/playwright/routing-events.generated.spec.ts`

**Step 1: Write failing tests**

In `web-frontend/tests/playwright/cmdk-shell.spec.ts`, update the nav labels:

```ts
for (const label of ['Notes', 'Search', 'Tags', 'Graph', 'Ask', 'Logger', 'Workflows', 'Daily', 'Configs']) {
  await expect(page.getByRole('button', { name: new RegExp(label) })).toBeVisible();
}
```

Add CmdK route expectation:

```ts
{ query: 'config', label: /^Open configs\b/, path: `/${vaultPath}/configs$` }
```

In `web-frontend/tests/playwright/routing-events.generated.spec.ts`, add a configs route assertion in the routing test:

```ts
await page.goto(`/${vaultName}/configs`);
await expectTopbar(page, vaultName, 'configs');
await expect(page.getByRole('heading', { name: 'Configs' })).toBeVisible();
```

**Step 2: Run to verify failure**

Run:

```bash
npx playwright test tests/playwright/cmdk-shell.spec.ts -g "sidebar app nav|every routed sidebar page" --project=chromium-light
```

Expected: FAIL because Configs route/nav does not exist.

---

### Task 7: Add Configs To Shared App Navigation

**Objective:** Add `configs` once to the shared nav source so drawer and CmdK both receive it.

**Files:**
- Modify: `web-frontend/src/lib/navigation/app-nav.ts`
- Test: `web-frontend/tests/playwright/cmdk-shell.spec.ts`

**Step 1: Implement nav entry**

```ts
export type AppNavPageId =
  | 'notes'
  | 'tags'
  | 'graph'
  | 'ask'
  | 'logger'
  | 'workflows'
  | 'daily'
  | 'configs';

// Append to appNavPages:
{
  id: 'configs',
  label: 'Configs',
  meta: 'settings',
  commandLabel: 'Open configs',
  commandHint: 'settings',
  href: (vaultName) => `/${vaultName}/configs`
}
```

**Step 2: Run partial test**

Run:

```bash
npx playwright test tests/playwright/cmdk-shell.spec.ts -g "every routed sidebar page" --project=chromium-light
```

Expected: Still FAIL because the route page is missing, but CmdK should now contain `Open configs`.

**Step 3: Commit**

Do not commit yet. Commit after Task 8 when the page exists.

---

### Task 8: Add Configs API Client And Page

**Objective:** Render a settings hub page with an Ask model credentials section.

**Files:**
- Create: `web-frontend/src/lib/configs/client.ts`
- Create: `web-frontend/src/routes/[vault]/configs/+page.svelte`
- Test: `web-frontend/tests/playwright/routing-events.generated.spec.ts`

**Step 1: Add typed client**

```ts
// web-frontend/src/lib/configs/client.ts
import { apiClient, apiGet } from '$lib/api/client.js';

export type AskCredentialProvider = {
  id: string;
  label: string;
  env_key: string;
  configured: boolean;
  fingerprint: string;
};

export type ConfigsResponse = {
  ask_credentials: {
    providers: AskCredentialProvider[];
  };
};

export function loadConfigs(vaultName: string) {
  return apiGet<ConfigsResponse>(`/api/v1/vault/${encodeURIComponent(vaultName)}/configs`);
}

export async function saveAskCredential(vaultName: string, providerId: string, apiKey: string) {
  const res = await apiClient(
    `/api/v1/vault/${encodeURIComponent(vaultName)}/configs/ask/credentials/${encodeURIComponent(providerId)}`,
    {
      method: 'PUT',
      body: JSON.stringify({ api_key: apiKey })
    }
  );
  if (!res.ok) throw new Error(`save credential -> ${res.status}`);
}

export async function deleteAskCredential(vaultName: string, providerId: string) {
  const res = await apiClient(
    `/api/v1/vault/${encodeURIComponent(vaultName)}/configs/ask/credentials/${encodeURIComponent(providerId)}`,
    { method: 'DELETE' }
  );
  if (!res.ok) throw new Error(`delete credential -> ${res.status}`);
}
```

**Step 2: Add page**

```svelte
<!-- web-frontend/src/routes/[vault]/configs/+page.svelte -->
<script lang="ts">
  import { page } from '$app/stores';
  import {
    deleteAskCredential,
    loadConfigs,
    saveAskCredential,
    type AskCredentialProvider
  } from '$lib/configs/client';

  let vaultName = $derived($page.params.vault ?? '');
  let loading = $state(true);
  let error = $state('');
  let providers = $state<AskCredentialProvider[]>([]);
  let values = $state<Record<string, string>>({});
  let saving = $state<Record<string, boolean>>({});

  $effect(() => {
    if (!vaultName) return;
    void refresh();
  });

  async function refresh() {
    loading = true;
    error = '';
    try {
      const data = await loadConfigs(vaultName);
      providers = data.ask_credentials.providers;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load configs.';
    } finally {
      loading = false;
    }
  }

  async function save(provider: AskCredentialProvider) {
    const value = (values[provider.id] ?? '').trim();
    if (!value) return;
    saving = { ...saving, [provider.id]: true };
    try {
      await saveAskCredential(vaultName, provider.id, value);
      values = { ...values, [provider.id]: '' };
      await refresh();
    } finally {
      saving = { ...saving, [provider.id]: false };
    }
  }

  async function remove(provider: AskCredentialProvider) {
    saving = { ...saving, [provider.id]: true };
    try {
      await deleteAskCredential(vaultName, provider.id);
      await refresh();
    } finally {
      saving = { ...saving, [provider.id]: false };
    }
  }
</script>

<svelte:head>
  <title>configs - {vaultName} - pkm</title>
</svelte:head>

<main class="configs-page">
  <h1>Configs</h1>
  <section aria-label="Ask model credentials">
    <h2>Ask Model Credentials</h2>
    {#if loading}
      <p>Loading configs...</p>
    {:else if error}
      <p class="error">{error}</p>
    {:else}
      {#each providers as provider (provider.id)}
        <form class="credential-row" onsubmit={(event) => { event.preventDefault(); void save(provider); }}>
          <div>
            <p>{provider.label}</p>
            <p>{provider.env_key} · {provider.configured ? provider.fingerprint : 'not configured'}</p>
          </div>
          <input
            type="password"
            autocomplete="off"
            aria-label={`${provider.label} API key`}
            value={values[provider.id] ?? ''}
            oninput={(event) =>
              (values = { ...values, [provider.id]: (event.currentTarget as HTMLInputElement).value })}
          />
          <button type="submit" disabled={saving[provider.id]}>Save</button>
          <button type="button" disabled={!provider.configured || saving[provider.id]} onclick={() => void remove(provider)}>
            Delete
          </button>
        </form>
      {/each}
    {/if}
  </section>
</main>
```

**Step 3: Run tests**

Run:

```bash
npx playwright test tests/playwright/cmdk-shell.spec.ts -g "sidebar app nav|every routed sidebar page" --project=chromium-light
npx playwright test tests/playwright/routing-events.generated.spec.ts -g "configs" --project=chromium-light
```

Expected: PASS after mock API is added in Task 9.

---

### Task 9: Add Configs Playwright Mock And Secret Non-Persistence Test

**Objective:** Prove the UI can save/delete keys and does not put the secret in browser storage.

**Files:**
- Modify: `web-frontend/tests/playwright/routing-events.generated.spec.ts`

**Step 1: Add mock API**

Inside `mockPkmApi`:

```ts
const credentialState: Record<string, string> = {};

const configsMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/configs$/);
if (configsMatch) {
  await json(route, {
    ask_credentials: {
      providers: [
        {
          id: 'google',
          label: 'Google Gemini',
          env_key: 'GEMINI_API_KEY',
          configured: Boolean(credentialState.google),
          fingerprint: credentialState.google ? '********1234' : ''
        },
        {
          id: 'openai',
          label: 'OpenAI',
          env_key: 'OPENAI_API_KEY',
          configured: Boolean(credentialState.openai),
          fingerprint: credentialState.openai ? '********1234' : ''
        }
      ]
    }
  });
  return;
}

const credentialMatch = path.match(
  /^\/api\/v1\/vault\/([^/]+)\/configs\/ask\/credentials\/([^/]+)$/
);
if (credentialMatch && route.request().method() === 'PUT') {
  const payload = route.request().postDataJSON() as { api_key?: string };
  credentialState[credentialMatch[2]] = payload.api_key ?? '';
  await json(route, { ok: true });
  return;
}
if (credentialMatch && route.request().method() === 'DELETE') {
  delete credentialState[credentialMatch[2]];
  await json(route, { ok: true });
  return;
}
```

**Step 2: Add test**

```ts
test('configs page stores ask API keys server-side without browser persistence', async ({ page }) => {
  await page.goto(`/${vaultName}/configs`);
  await expectTopbar(page, vaultName, 'configs');
  await expect(page.getByRole('heading', { name: 'Configs' })).toBeVisible();

  await page.getByLabel('OpenAI API key').fill('sk-test-browser-secret');
  await page.getByRole('button', { name: 'Save' }).nth(1).click();
  await expect(page.getByText('********1234')).toBeVisible();
  await expect(page.getByLabel('OpenAI API key')).toHaveValue('');

  const browserStorage = await page.evaluate(() => ({
    local: JSON.stringify(localStorage),
    session: JSON.stringify(sessionStorage)
  }));
  expect(browserStorage.local).not.toContain('sk-test-browser-secret');
  expect(browserStorage.session).not.toContain('sk-test-browser-secret');
});
```

**Step 3: Run test**

Run: `npx playwright test tests/playwright/routing-events.generated.spec.ts -g "configs page stores" --project=chromium-light`

Expected: PASS.

**Step 4: Commit frontend page**

```bash
git add web-frontend/src/lib/navigation/app-nav.ts web-frontend/src/lib/configs/client.ts web-frontend/src/routes/[vault]/configs/+page.svelte web-frontend/tests/playwright/cmdk-shell.spec.ts web-frontend/tests/playwright/routing-events.generated.spec.ts
git commit -m "Add Configs page for Ask credentials"
```

Use the repo Lore trailer format in the commit body.

---

### Task 10: Add Credential Test Endpoint

**Objective:** Let users verify whether a saved key can satisfy the provider environment check.

**Files:**
- Modify: `cli/src/pkm/web/routes/configs.py`
- Modify: `cli/tests/test_web_configs.py`
- Modify: `web-frontend/src/lib/configs/client.ts`
- Modify: `web-frontend/src/routes/[vault]/configs/+page.svelte`

**Step 1: Backend failing test**

```python
@pytest.mark.anyio
async def test_credential_test_reports_missing_or_ok(app, tmp_vault, monkeypatch):
    class FakeStore:
        def get(self, env_key):
            return "sk-test-secret"

    monkeypatch.setattr("pkm.web.routes.configs.SecretStore", lambda: FakeStore())
    monkeypatch.setattr(
        "pkm.web.routes.configs.validate_provider_environment",
        lambda provider, key: (True, "ready"),
    )

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/configs/ask/credentials/openai/test",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        body = await resp.json()

    assert resp.status == 200
    assert body == {"ok": True, "message": "ready"}
```

**Step 2: Implement validation helper**

```python
def validate_provider_environment(provider: dict[str, str], api_key: str) -> tuple[bool, str]:
    env_key = provider["env_key"]
    old = os.environ.get(env_key)
    os.environ[env_key] = api_key
    try:
        import litellm

        validation = litellm.validate_environment(provider["model_probe"])
        ok = bool(validation.get("keys_in_environment", True))
        missing = ", ".join(validation.get("missing_keys", []))
        return ok, "ready" if ok else f"missing: {missing}"
    finally:
        if old is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = old
```

Add `model_probe` to provider registry:

```python
"openai": {"label": "OpenAI", "env_key": "OPENAI_API_KEY", "model_probe": "gpt-5.4-mini"}
```

**Step 3: Frontend test button**

Add `testAskCredential` to `web-frontend/src/lib/configs/client.ts` and a `Test` button in the page. Display only `ready` or sanitized failure text; never echo the key.

**Step 4: Run tests**

Run:

```bash
uv run --project cli --extra web --extra search pytest cli/tests/test_web_configs.py -q
npx playwright test tests/playwright/routing-events.generated.spec.ts -g "configs" --project=chromium-light
```

Expected: PASS.

**Step 5: Commit**

```bash
git add cli/src/pkm/secrets.py cli/src/pkm/web/routes/configs.py cli/tests/test_web_configs.py web-frontend/src/lib/configs/client.ts web-frontend/src/routes/[vault]/configs/+page.svelte web-frontend/tests/playwright/routing-events.generated.spec.ts
git commit -m "Add Ask credential verification"
```

Use the repo Lore trailer format in the commit body.

---

### Task 11: Full Verification

**Objective:** Prove the end-to-end feature works and does not regress existing Ask behavior.

**Files:**
- No edits unless failures require fixes.

**Step 1: Run backend tests**

```bash
uv run --project cli --extra web --extra search pytest cli/tests/test_secrets.py cli/tests/test_web_configs.py cli/tests/test_web_ask_sse.py -q
```

Expected: PASS.

**Step 2: Run frontend tests**

```bash
npx vitest run src/lib/ask/session.svelte.test.ts
npx playwright test tests/playwright/cmdk-shell.spec.ts --project=chromium-light
npx playwright test tests/playwright/routing-events.generated.spec.ts -g "configs|ask input states" --project=chromium-light
npm run build
```

Expected: PASS.

**Step 3: Manual smoke check**

Start/restart the daemon:

```bash
systemctl --user restart pkm-web
curl -fsS -I http://127.0.0.1:7420/
```

Expected: HTTP 200.

Open `/{vault}/configs`, save a fake-looking key in a test environment, confirm:

- Input clears after save.
- Status changes to configured.
- Page source/localStorage/sessionStorage do not contain the raw key.
- Ask options resolve after a real key is configured.

**Step 4: Final commit if any fixes were needed**

Commit only files touched by fixes, using Lore trailer format.

---

## Implementation Notes

- Do not store API keys in `localStorage`, `sessionStorage`, IndexedDB, URL params, service worker cache, or transcript history.
- Do not return raw secrets from any API response.
- Do not log request bodies for credential routes.
- The fallback file exists only for local single-user mode and must always be `0600`.
- `Configs` is the settings hub; future general settings should add new sections under this page instead of creating one-off settings pages.
- If `keyring` is unavailable or unusable on a headless Linux session, fallback file storage is expected behavior, not a failure.
