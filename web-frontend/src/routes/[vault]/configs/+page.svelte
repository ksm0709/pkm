<script lang="ts">
  import { page } from '$app/stores';
  import {
    deleteAskCredential,
    loadConfigs,
    saveAskCredential,
    type AskCredentialProvider
  } from '$lib/configs/client';

  let vaultName = $derived($page.params.vault);
  let providers = $state<AskCredentialProvider[]>([]);
  let inputs = $state<Record<string, string>>({});
  let messages = $state<Record<string, string>>({});
  let errors = $state<Record<string, string>>({});
  let busy = $state<Record<string, boolean>>({});
  let loading = $state(true);
  let loadError = $state('');
  let loadSequence = 0;
  let loadedVault = '';

  async function refreshConfigs(vault: string) {
    const sequence = ++loadSequence;
    loading = true;
    loadError = '';
    try {
      const configs = await loadConfigs(vault);
      if (sequence !== loadSequence || vaultName !== vault) return;
      providers = configs.ask_credentials?.providers ?? [];
    } catch (e) {
      if (sequence !== loadSequence || vaultName !== vault) return;
      loadError = e instanceof Error ? e.message : 'Failed to load configs.';
      providers = [];
    } finally {
      if (sequence === loadSequence && vaultName === vault) {
        loading = false;
      }
    }
  }

  function inputValue(providerId: string) {
    return inputs[providerId] ?? '';
  }

  function updateInput(providerId: string, value: string) {
    inputs = { ...inputs, [providerId]: value };
  }

  function setProviderState(providerId: string, state: { message?: string; error?: string; busy?: boolean }) {
    if (state.message !== undefined) messages = { ...messages, [providerId]: state.message };
    if (state.error !== undefined) errors = { ...errors, [providerId]: state.error };
    if (state.busy !== undefined) busy = { ...busy, [providerId]: state.busy };
  }

  async function saveProvider(provider: AskCredentialProvider) {
    const vault = vaultName;
    const apiKey = inputValue(provider.id);
    if (!apiKey) {
      setProviderState(provider.id, {
        message: '',
        error: `${provider.label} API key is required.`
      });
      return;
    }

    setProviderState(provider.id, { message: '', error: '', busy: true });
    try {
      await saveAskCredential(vault, provider.id, apiKey);
      if (vaultName !== vault) return;
      updateInput(provider.id, '');
      await refreshConfigs(vault);
      if (vaultName !== vault) return;
      setProviderState(provider.id, { message: 'Saved', error: '' });
    } catch {
      if (vaultName !== vault) return;
      setProviderState(provider.id, {
        message: '',
        error: `Failed to save ${provider.label} credential.`
      });
    } finally {
      if (vaultName === vault) {
        setProviderState(provider.id, { busy: false });
      }
    }
  }

  async function deleteProvider(provider: AskCredentialProvider) {
    const vault = vaultName;
    setProviderState(provider.id, { message: '', error: '', busy: true });
    try {
      await deleteAskCredential(vault, provider.id);
      if (vaultName !== vault) return;
      await refreshConfigs(vault);
      if (vaultName !== vault) return;
      setProviderState(provider.id, { message: 'Deleted', error: '' });
    } catch {
      if (vaultName !== vault) return;
      setProviderState(provider.id, {
        message: '',
        error: `Failed to delete ${provider.label} credential.`
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
                  <span class:configured={provider.configured} class="provider-status">
                    {provider.configured ? 'configured' : 'not configured'}
                  </span>
                  <span class="provider-fingerprint">
                    {provider.fingerprint ?? 'none'}
                  </span>
                  <label class="secret-field">
                    <span>{provider.label} API key</span>
                    <input
                      type="password"
                      autocomplete="off"
                      value={inputValue(provider.id)}
                      aria-label={`${provider.label} API key`}
                      oninput={(event) =>
                        updateInput(provider.id, (event.currentTarget as HTMLInputElement).value)}
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

  <section class="settings-section vault-settings" aria-labelledby="vault-settings-heading">
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

  .secret-field input:focus-visible,
  .provider-actions button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .provider-actions {
    display: flex;
    gap: var(--space-2, 8px);
    justify-content: flex-end;
  }

  .provider-actions button {
    min-height: 34px;
    padding: 0 var(--space-3, 12px);
    color: var(--text);
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 4px;
    cursor: pointer;
  }

  .provider-actions button:hover {
    border-color: var(--accent);
  }

  .provider-actions button:disabled {
    cursor: progress;
    opacity: 0.62;
  }

  .status-msg,
  .provider-message {
    margin: var(--space-2, 8px) 0 0;
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-muted);
  }

  .status-msg.error,
  .provider-message.error {
    color: var(--signal-danger, #c0392b);
  }

  .status-msg.faint {
    color: var(--text-faint);
  }

  @media (max-width: 920px) {
    .provider-head {
      display: none;
    }

    .provider-main {
      grid-template-columns: minmax(0, 1fr);
      gap: var(--space-2, 8px);
    }

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
