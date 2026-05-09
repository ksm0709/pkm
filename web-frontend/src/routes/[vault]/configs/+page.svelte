<script lang="ts">
  import { page } from "$app/stores";
  import {
    deleteAskCredential,
    loadConfigs,
    saveConfigSetting,
    saveAskCredential,
    type AskCredentialProvider,
    type ConfigSetting,
  } from "$lib/configs/client";

  let vaultName = $derived($page.params.vault);
  let settings = $state<ConfigSetting[]>([]);
  let settingValues = $state<Record<string, string>>({});
  let settingDirty = $state<Record<string, boolean>>({});
  let settingMessages = $state<Record<string, string>>({});
  let settingErrors = $state<Record<string, string>>({});
  let settingBusy = $state<Record<string, boolean>>({});
  let providers = $state<AskCredentialProvider[]>([]);
  let inputs = $state<Record<string, string>>({});
  let messages = $state<Record<string, string>>({});
  let errors = $state<Record<string, string>>({});
  let busy = $state<Record<string, boolean>>({});
  let loading = $state(true);
  let loadError = $state("");
  let loadSequence = 0;
  let loadedVault = "";

  async function refreshConfigs(vault: string) {
    const sequence = ++loadSequence;
    loading = true;
    loadError = "";
    try {
      const configs = await loadConfigs(vault);
      if (sequence !== loadSequence || vaultName !== vault) return;
      const nextSettings = configs.settings ?? [];
      settings = nextSettings;
      syncSettingValues(nextSettings);
      providers = configs.ask_credentials?.providers ?? [];
    } catch (e) {
      if (sequence !== loadSequence || vaultName !== vault) return;
      loadError = e instanceof Error ? e.message : "Failed to load configs.";
      settings = [];
      providers = [];
    } finally {
      if (sequence === loadSequence && vaultName === vault) {
        loading = false;
      }
    }
  }

  function syncSettingValues(nextSettings: ConfigSetting[]) {
    const nextValues = { ...settingValues };
    const nextKeys = new Set(nextSettings.map((setting) => setting.key));
    for (const setting of nextSettings) {
      if (!settingDirty[setting.key]) {
        nextValues[setting.key] = setting.value ?? "";
      }
    }
    for (const key of Object.keys(nextValues)) {
      if (!nextKeys.has(key)) delete nextValues[key];
    }
    settingValues = nextValues;
  }

  function settingValue(setting: ConfigSetting) {
    return settingValues[setting.key] ?? setting.value ?? "";
  }

  function updateSettingValue(settingKey: string, value: string) {
    settingValues = { ...settingValues, [settingKey]: value };
    settingDirty = { ...settingDirty, [settingKey]: true };
  }

  function setSettingState(
    settingKey: string,
    state: {
      message?: string;
      error?: string;
      busy?: boolean;
      dirty?: boolean;
    },
  ) {
    if (state.message !== undefined) {
      settingMessages = { ...settingMessages, [settingKey]: state.message };
    }
    if (state.error !== undefined) {
      settingErrors = { ...settingErrors, [settingKey]: state.error };
    }
    if (state.busy !== undefined) {
      settingBusy = { ...settingBusy, [settingKey]: state.busy };
    }
    if (state.dirty !== undefined) {
      settingDirty = { ...settingDirty, [settingKey]: state.dirty };
    }
  }

  async function saveSetting(setting: ConfigSetting) {
    const vault = vaultName;
    const value = settingValue(setting);
    setSettingState(setting.key, { message: "", error: "", busy: true });
    try {
      const updated = await saveConfigSetting(
        vault,
        setting.key,
        setting.input_type === "boolean" ? value === "true" : value,
      );
      if (vaultName !== vault) return;
      settings = settings.map((item) =>
        item.key === updated.key ? updated : item,
      );
      settingValues = { ...settingValues, [updated.key]: updated.value ?? "" };
      setSettingState(updated.key, {
        message: "Saved",
        error: "",
        dirty: false,
      });
    } catch {
      if (vaultName !== vault) return;
      setSettingState(setting.key, {
        message: "",
        error: `Failed to save ${setting.key}.`,
      });
    } finally {
      if (vaultName === vault) {
        setSettingState(setting.key, { busy: false });
      }
    }
  }

  async function resetSetting(setting: ConfigSetting) {
    const vault = vaultName;
    setSettingState(setting.key, { message: "", error: "", busy: true });
    try {
      const updated = await saveConfigSetting(vault, setting.key, null);
      if (vaultName !== vault) return;
      settings = settings.map((item) =>
        item.key === updated.key ? updated : item,
      );
      settingValues = { ...settingValues, [updated.key]: updated.value ?? "" };
      setSettingState(updated.key, {
        message: "Reset",
        error: "",
        dirty: false,
      });
    } catch {
      if (vaultName !== vault) return;
      setSettingState(setting.key, {
        message: "",
        error: `Failed to reset ${setting.key}.`,
      });
    } finally {
      if (vaultName === vault) {
        setSettingState(setting.key, { busy: false });
      }
    }
  }

  function inputValue(providerId: string) {
    return inputs[providerId] ?? "";
  }

  function updateInput(providerId: string, value: string) {
    inputs = { ...inputs, [providerId]: value };
  }

  function setProviderState(
    providerId: string,
    state: { message?: string; error?: string; busy?: boolean },
  ) {
    if (state.message !== undefined)
      messages = { ...messages, [providerId]: state.message };
    if (state.error !== undefined)
      errors = { ...errors, [providerId]: state.error };
    if (state.busy !== undefined) busy = { ...busy, [providerId]: state.busy };
  }

  async function saveProvider(provider: AskCredentialProvider) {
    const vault = vaultName;
    const apiKey = inputValue(provider.id);
    if (!apiKey) {
      setProviderState(provider.id, {
        message: "",
        error: `${provider.label} API key is required.`,
      });
      return;
    }

    setProviderState(provider.id, { message: "", error: "", busy: true });
    try {
      await saveAskCredential(vault, provider.id, apiKey);
      if (vaultName !== vault) return;
      updateInput(provider.id, "");
      await refreshConfigs(vault);
      if (vaultName !== vault) return;
      setProviderState(provider.id, { message: "Saved", error: "" });
    } catch {
      if (vaultName !== vault) return;
      setProviderState(provider.id, {
        message: "",
        error: `Failed to save ${provider.label} credential.`,
      });
    } finally {
      if (vaultName === vault) {
        setProviderState(provider.id, { busy: false });
      }
    }
  }

  async function deleteProvider(provider: AskCredentialProvider) {
    const vault = vaultName;
    setProviderState(provider.id, { message: "", error: "", busy: true });
    try {
      await deleteAskCredential(vault, provider.id);
      if (vaultName !== vault) return;
      await refreshConfigs(vault);
      if (vaultName !== vault) return;
      setProviderState(provider.id, { message: "Deleted", error: "" });
    } catch {
      if (vaultName !== vault) return;
      setProviderState(provider.id, {
        message: "",
        error: `Failed to delete ${provider.label} credential.`,
      });
    } finally {
      if (vaultName === vault) {
        setProviderState(provider.id, { busy: false });
      }
    }
  }

  $effect(() => {
    const vault = vaultName;
    if (!vault) return;
    if (loadedVault !== vault) {
      loadedVault = vault;
      settingValues = {};
      settingDirty = {};
      settingMessages = {};
      settingErrors = {};
      settingBusy = {};
      inputs = {};
      messages = {};
      errors = {};
      busy = {};
    }
    void refreshConfigs(vault);
  });
</script>

<svelte:head>
  <title>Configs — {vaultName} — pkm</title>
</svelte:head>

<main class="configs-page">
  <header class="configs-header">
    <span class="meta-rail">CONFIGS</span>
    <h1>Configs</h1>
  </header>

  <section class="settings-section" aria-labelledby="global-settings-heading">
    <div class="section-heading">
      <h2 id="global-settings-heading">Global Settings</h2>
      <span>user-global</span>
    </div>

    {#if loading}
      <p class="status-msg">Loading…</p>
    {:else if loadError}
      <p class="status-msg error">{loadError}</p>
    {:else if settings.length === 0}
      <p class="status-msg faint">No editable PKM settings are available.</p>
    {:else}
      <div class="config-ledger" aria-label="PKM config settings">
        <div class="config-head">
          <span>KEY</span>
          <span>VALUE</span>
          <span>DESCRIPTION</span>
          <span>ACTIONS</span>
        </div>
        <ul class="config-list">
          {#each settings as setting (setting.key)}
            <li class="config-row" data-setting-key={setting.key}>
              <div class="config-main">
                <span class="config-key">{setting.key}</span>
                <label class="config-field">
                  <span>{setting.key} value</span>
                  {#if setting.input_type === "boolean"}
                    <input
                      type="checkbox"
                      checked={settingValue(setting) === "true"}
                      aria-label={`${setting.key} value`}
                      onchange={(event) =>
                        updateSettingValue(
                          setting.key,
                          (event.currentTarget as HTMLInputElement).checked
                            ? "true"
                            : "false",
                        )}
                    />
                  {:else}
                    <input
                      type={setting.input_type === "number" ? "number" : "text"}
                      value={settingValue(setting)}
                      aria-label={`${setting.key} value`}
                      list={setting.options.length
                        ? `${setting.key}-options`
                        : undefined}
                      oninput={(event) =>
                        updateSettingValue(
                          setting.key,
                          (event.currentTarget as HTMLInputElement).value,
                        )}
                    />
                    {#if setting.options.length}
                      <datalist id={`${setting.key}-options`}>
                        {#each setting.options as option}
                          <option value={option}></option>
                        {/each}
                      </datalist>
                    {/if}
                  {/if}
                </label>
                <span class="config-description">{setting.description}</span>
                <div class="config-actions">
                  <button
                    type="button"
                    aria-label={`Save ${setting.key}`}
                    disabled={settingBusy[setting.key] ||
                      !settingDirty[setting.key]}
                    onclick={() => void saveSetting(setting)}
                  >
                    Save
                  </button>
                  <button
                    type="button"
                    aria-label={`Reset ${setting.key}`}
                    disabled={settingBusy[setting.key] || !setting.configured}
                    onclick={() => void resetSetting(setting)}
                  >
                    Reset
                  </button>
                </div>
              </div>
              {#if settingMessages[setting.key]}
                <p class="config-message">{settingMessages[setting.key]}</p>
              {/if}
              {#if settingErrors[setting.key]}
                <p class="config-message error">{settingErrors[setting.key]}</p>
              {/if}
            </li>
          {/each}
        </ul>
      </div>
    {/if}

    <section class="ask-credentials" aria-labelledby="ask-credentials-heading">
      <div class="section-heading nested">
        <h3 id="ask-credentials-heading">Ask Model Credentials</h3>
        <span>stored server-side</span>
      </div>

      {#if loading}
        <p class="status-msg">Loading…</p>
      {:else if loadError}
        <p class="status-msg error">{loadError}</p>
      {:else if providers.length === 0}
        <p class="status-msg faint">No credential providers configured.</p>
      {:else}
        <div class="provider-ledger" aria-label="Ask credential providers">
          <div class="provider-head">
            <span>PROVIDER</span>
            <span>ENV KEY</span>
            <span>STATUS</span>
            <span>FINGERPRINT</span>
            <span>SECRET</span>
            <span>ACTIONS</span>
          </div>
          <ul class="provider-list">
            {#each providers as provider (provider.id)}
              <li class="provider-row" data-provider-id={provider.id}>
                <div class="provider-main">
                  <span class="provider-label">{provider.label}</span>
                  <span class="provider-env">{provider.env_key}</span>
                  <span
                    class:configured={provider.configured}
                    class="provider-status"
                  >
                    {provider.configured ? "configured" : "not configured"}
                  </span>
                  <span class="provider-fingerprint">
                    {provider.fingerprint ?? "none"}
                  </span>
                  <label class="secret-field">
                    <span>{provider.label} API key</span>
                    <input
                      type="password"
                      autocomplete="off"
                      value={inputValue(provider.id)}
                      aria-label={`${provider.label} API key`}
                      oninput={(event) =>
                        updateInput(
                          provider.id,
                          (event.currentTarget as HTMLInputElement).value,
                        )}
                    />
                  </label>
                  <div class="provider-actions">
                    <button
                      type="button"
                      aria-label={`Save ${provider.label} credential`}
                      disabled={busy[provider.id]}
                      onclick={() => void saveProvider(provider)}
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      aria-label={`Delete ${provider.label} credential`}
                      disabled={busy[provider.id]}
                      onclick={() => void deleteProvider(provider)}
                    >
                      Delete
                    </button>
                  </div>
                </div>
                {#if messages[provider.id]}
                  <p class="provider-message">{messages[provider.id]}</p>
                {/if}
                {#if errors[provider.id]}
                  <p class="provider-message error">{errors[provider.id]}</p>
                {/if}
              </li>
            {/each}
          </ul>
        </div>
      {/if}
    </section>
  </section>

  <section
    class="settings-section vault-settings"
    aria-labelledby="vault-settings-heading"
  >
    <div class="section-heading">
      <h2 id="vault-settings-heading">Vault Settings</h2>
      <span>{vaultName}</span>
    </div>
    <p class="status-msg faint">No vault-specific settings are available.</p>
  </section>
</main>

<style>
  .configs-page {
    width: min(1180px, calc(100vw - 64px));
    margin: 0 auto;
    padding: var(--space-6, 32px) 0 var(--space-8, 64px);
  }

  .configs-header {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: var(--space-4, 16px);
    padding-bottom: var(--space-4, 16px);
    border-bottom: 1px solid var(--border);
  }

  .configs-header h1,
  .section-heading h2,
  .section-heading h3 {
    margin: 0;
    font-family: var(--font-mono);
    color: var(--text);
  }

  .configs-header h1 {
    font-size: var(--type-title-size, 28px);
    font-weight: 600;
  }

  .meta-rail,
  .section-heading span,
  .config-head,
  .config-key,
  .config-field,
  .config-actions button,
  .config-message,
  .provider-head,
  .provider-env,
  .provider-status,
  .status-msg,
  .provider-message,
  .secret-field,
  .provider-actions button {
    font-family: var(--font-mono);
  }

  .meta-rail,
  .section-heading span {
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-faint);
  }

  .settings-section {
    padding: var(--space-6, 32px) 0;
    border-bottom: 1px solid var(--border);
  }

  .section-heading {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-4, 16px);
    margin-bottom: var(--space-4, 16px);
  }

  .section-heading h2 {
    font-size: 18px;
  }

  .section-heading h3 {
    font-size: 15px;
  }

  .section-heading.nested {
    margin-bottom: var(--space-3, 12px);
  }

  .ask-credentials {
    padding-top: var(--space-4, 16px);
    border-top: 1px solid var(--border);
  }

  .provider-ledger {
    border-top: 1px solid var(--border);
  }

  .config-ledger {
    border-top: 1px solid var(--border);
    margin-bottom: var(--space-5, 24px);
  }

  .config-head,
  .config-main {
    display: grid;
    grid-template-columns:
      minmax(150px, 0.9fr) minmax(190px, 1fr) minmax(260px, 1.4fr)
      168px;
    gap: var(--space-4, 16px);
    align-items: center;
  }

  .config-head {
    min-height: 34px;
    border-bottom: 1px solid var(--border);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-faint);
  }

  .config-list {
    display: flex;
    flex-direction: column;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .config-row {
    min-width: 0;
    padding: var(--space-3, 12px) 0;
    border-bottom: 1px solid var(--border);
  }

  .config-key,
  .config-description {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .config-key {
    color: var(--text);
    white-space: nowrap;
  }

  .config-description {
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-muted);
  }

  .config-description {
    line-height: 1.45;
  }

  .config-field {
    display: grid;
    gap: var(--space-1, 4px);
    min-width: 0;
    font-size: var(--type-chrome-sm-size, 11px);
    color: var(--text-faint);
  }

  .config-field input[type="text"],
  .config-field input[type="number"] {
    min-width: 0;
    height: 34px;
    padding: 0 var(--space-2, 8px);
    color: var(--text);
    background: var(--surface, var(--bg));
    border: 1px solid var(--border);
    border-radius: 4px;
  }

  .config-field input[type="checkbox"] {
    width: 22px;
    height: 22px;
    accent-color: var(--accent);
  }

  .provider-head,
  .provider-main {
    display: grid;
    grid-template-columns:
      minmax(120px, 0.9fr) minmax(150px, 1fr) minmax(120px, 0.8fr)
      minmax(120px, 0.9fr) minmax(180px, 1.2fr) 150px;
    gap: var(--space-4, 16px);
    align-items: center;
  }

  .provider-head {
    min-height: 34px;
    border-bottom: 1px solid var(--border);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-faint);
  }

  .provider-list {
    display: flex;
    flex-direction: column;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .provider-row {
    min-width: 0;
    padding: var(--space-3, 12px) 0;
    border-bottom: 1px solid var(--border);
  }

  .provider-label,
  .provider-env,
  .provider-status,
  .provider-fingerprint {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .provider-label {
    color: var(--text);
  }

  .provider-env,
  .provider-status,
  .provider-fingerprint {
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-muted);
  }

  .provider-status.configured {
    color: var(--accent);
  }

  .secret-field {
    display: grid;
    gap: var(--space-1, 4px);
    min-width: 0;
    font-size: var(--type-chrome-sm-size, 11px);
    color: var(--text-faint);
  }

  .secret-field input {
    min-width: 0;
    height: 34px;
    padding: 0 var(--space-2, 8px);
    color: var(--text);
    background: var(--surface, var(--bg));
    border: 1px solid var(--border);
    border-radius: 4px;
  }

  .config-field input:focus-visible,
  .config-actions button:focus-visible,
  .secret-field input:focus-visible,
  .provider-actions button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .config-actions,
  .provider-actions {
    display: flex;
    gap: var(--space-2, 8px);
    justify-content: flex-end;
  }

  .config-actions button,
  .provider-actions button {
    min-height: 34px;
    padding: 0 var(--space-3, 12px);
    color: var(--text);
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 4px;
    cursor: pointer;
  }

  .config-actions button:hover,
  .provider-actions button:hover {
    border-color: var(--accent);
  }

  .config-actions button:disabled,
  .provider-actions button:disabled {
    cursor: progress;
    opacity: 0.62;
  }

  .status-msg,
  .config-message,
  .provider-message {
    margin: var(--space-2, 8px) 0 0;
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-muted);
  }

  .status-msg.error,
  .config-message.error,
  .provider-message.error {
    color: var(--signal-danger, #c0392b);
  }

  .status-msg.faint {
    color: var(--text-faint);
  }

  @media (max-width: 920px) {
    .config-head,
    .provider-head {
      display: none;
    }

    .config-main,
    .provider-main {
      grid-template-columns: minmax(0, 1fr);
      gap: var(--space-2, 8px);
    }

    .config-actions,
    .provider-actions {
      justify-content: flex-start;
    }
  }

  @media (max-width: 760px) {
    .configs-page {
      width: min(100%, calc(100vw - 32px));
    }

    .configs-header,
    .section-heading {
      align-items: start;
      flex-direction: column;
      gap: var(--space-2, 8px);
    }
  }
</style>
