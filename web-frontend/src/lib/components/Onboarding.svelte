<script lang="ts">
  import { goto } from '$app/navigation';
  import { apiClient } from '$lib/api/client.js';

  let token = $state('');
  let remember = $state(true);
  let error = $state('');
  let loading = $state(false);

  async function handleSubmit(e: SubmitEvent) {
    e.preventDefault();
    if (!token.trim()) return;

    loading = true;
    error = '';

    try {
      // Validate token against the API
      const result = await apiClient('/api/v1/vaults', { token: token.trim() });

      if (result.ok) {
        // Persist token
        if (remember) {
          localStorage.setItem('pkm.token', token.trim());
        } else {
          sessionStorage.setItem('pkm.token', token.trim());
          localStorage.removeItem('pkm.token');
        }

        // Navigate to last vault or first available
        const lastVault = localStorage.getItem('pkm.lastVault');
        if (lastVault) {
          await goto(`/${lastVault}`);
        } else {
          const vaults: string[] = await result.json().catch(() => []);
          if (Array.isArray(vaults) && vaults.length > 0) {
            await goto(`/${vaults[0]}`);
          } else {
            await goto('/');
          }
        }
      } else {
        error = result.status === 401 ? 'Invalid token.' : 'Connection failed.';
      }
    } catch {
      error = 'Cannot reach daemon. Is pkm running?';
    } finally {
      loading = false;
    }
  }
</script>

<div class="onboarding">
  <div class="reading-column onboarding-inner">
    <h1 class="wordmark">pkm</h1>
    <p class="tagline">Paste your access token to connect.</p>

    <form onsubmit={handleSubmit} class="form">
      <div class="field">
        <label class="field-label" for="token-input">Access token</label>
        <input
          id="token-input"
          class="token-input"
          type="password"
          placeholder="pkm_…"
          bind:value={token}
          autocomplete="off"
          spellcheck="false"
          disabled={loading}
        />
      </div>

      <label class="remember-label">
        <input type="checkbox" bind:checked={remember} disabled={loading} />
        <span>Remember this device</span>
      </label>

      {#if error}
        <p class="error-msg" role="alert">{error}</p>
      {/if}

      <button class="submit-btn" type="submit" disabled={loading || !token.trim()}>
        {loading ? 'Connecting…' : 'Connect'}
      </button>
    </form>
  </div>
</div>

<style>
  .onboarding {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: var(--bg);
    padding: var(--space-6, 32px) var(--space-4, 16px);
  }

  .onboarding-inner {
    width: 100%;
  }

  .wordmark {
    font-family: var(--font-display);
    font-size: 32px;
    font-weight: 600;
    line-height: 1;
    letter-spacing: -0.02em;
    color: var(--text);
    margin-bottom: var(--space-2, 8px);
  }

  .tagline {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-muted);
    margin-bottom: var(--space-6, 32px);
  }

  .form {
    display: flex;
    flex-direction: column;
    gap: var(--space-4, 16px);
    max-width: 480px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-1, 4px);
  }

  .field-label {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: var(--type-chrome-sm-weight, 500);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-faint);
  }

  .token-input {
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    color: var(--text);
    background-color: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-none, 0);
    padding: var(--space-2, 8px) var(--space-3, 12px);
    width: 100%;
    outline: none;
    caret-color: var(--accent);
    transition: border-color var(--dur-fast, 120ms) var(--ease-out);
  }

  .token-input:focus {
    border-color: var(--accent);
  }

  .token-input::placeholder {
    color: var(--text-faint);
  }

  .remember-label {
    display: flex;
    align-items: center;
    gap: var(--space-2, 8px);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-muted);
    cursor: pointer;
  }

  .remember-label input[type="checkbox"] {
    accent-color: var(--accent);
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }

  .error-msg {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    color: #c0392b;
  }

  .submit-btn {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    font-weight: 500;
    color: var(--bg);
    background-color: var(--accent);
    border: none;
    border-radius: var(--radius-none, 0);
    padding: var(--space-2, 8px) var(--space-4, 16px);
    cursor: pointer;
    align-self: flex-start;
    transition: opacity var(--dur-fast, 120ms) var(--ease-out);
  }

  .submit-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .submit-btn:not(:disabled):hover {
    opacity: 0.85;
  }
</style>
