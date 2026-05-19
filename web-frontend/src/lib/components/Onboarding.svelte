<script lang="ts">
  import { goto } from "$app/navigation";
  import { readRememberedVault } from "$lib/vault/remembered-vault";

  let password = $state("");
  let remember = $state(true);
  let error = $state("");
  let loading = $state(false);

  async function handleSubmit(e: SubmitEvent) {
    e.preventDefault();
    if (!password) return;

    loading = true;
    error = "";

    try {
      const result = await fetch("/api/v1/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password, remember }),
      });

      if (result.ok) {
        localStorage.removeItem("pkm.token");
        sessionStorage.removeItem("pkm.token");

        // Navigate to last vault or first available
        const lastVault = readRememberedVault();
        if (lastVault) {
          await goto(`/${lastVault}/logger`);
        } else {
          const data = await result.json().catch(() => ({ vaults: [] }));
          const vaults = Array.isArray(data?.vaults) ? data.vaults : [];
          if (vaults.length > 0) {
            await goto(`/${vaults[0].name}/logger`);
          } else {
            await goto("/");
          }
        }
      } else {
        error =
          result.status === 401
            ? "Invalid password."
            : "Password login is not configured.";
      }
    } catch {
      error = "Cannot reach daemon. Is pkm running?";
    } finally {
      loading = false;
    }
  }
</script>

<div class="onboarding">
  <div class="login-console">
    <section class="signal-block" aria-labelledby="login-title">
      <p class="eyebrow">local knowledge station</p>
      <h1 id="login-title" class="wordmark">pkm</h1>
      <p class="tagline">
        Authenticate to the local daemon and reopen your thinking cockpit.
      </p>

      <dl class="meta-grid" aria-label="Session requirements">
        <div>
          <dt>local daemon</dt>
          <dd>required</dd>
        </div>
        <div>
          <dt>session cookie</dt>
          <dd>{remember ? "persistent" : "session"}</dd>
        </div>
      </dl>
    </section>

    <form onsubmit={handleSubmit} class="form" aria-label="Password login">
      <div class="form-rail" aria-hidden="true"></div>
      <div class="form-header">
        <p class="form-kicker">entry console</p>
        <p class="form-copy">
          Password-only access. Existing cookie flow is preserved.
        </p>
      </div>

      <div class="field">
        <label class="field-label" for="password-input">Password</label>
        <input
          id="password-input"
          class="password-input"
          type="password"
          bind:value={password}
          autocomplete="current-password"
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

      <button class="submit-btn" type="submit" disabled={loading || !password}>
        <span>{loading ? "Signing in…" : "Sign in"}</span>
      </button>
    </form>
  </div>
</div>

<style>
  .onboarding {
    --bg: #090b0d;
    --bg-elev: #101419;
    --surface: #101419;
    --text: #e8ecef;
    --text-muted: #9aa6ad;
    --text-faint: #5f6970;
    --border: rgba(159, 177, 188, 0.2);
    --accent: #ecaa4a;
    --accent-bg: rgba(236, 170, 74, 0.12);
    --signal: #ecaa4a;
    --signal-danger: #ff6b5f;
    --rail: rgba(236, 170, 74, 0.58);
    --grid-line: rgba(159, 177, 188, 0.055);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    background: var(--bg, #090b0d);
    padding: var(--space-7, 48px) var(--space-4, 16px);
  }

  .login-console {
    width: min(960px, 100%);
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(320px, 440px);
    gap: clamp(24px, 6vw, 80px);
    align-items: center;
    animation: login-reveal var(--dur-base, 200ms) var(--ease-out) both;
  }

  .signal-block {
    position: relative;
    min-width: 0;
    padding-left: var(--space-5, 24px);
    border-left: 1px solid var(--rail, rgba(236, 170, 74, 0.58));
  }

  .signal-block::before {
    content: "";
    position: absolute;
    left: -1px;
    top: 0;
    width: 1px;
    height: 72px;
    background: var(--signal, var(--accent, #ecaa4a));
  }

  .eyebrow,
  .form-kicker,
  .field-label,
  .remember-label,
  .error-msg,
  .submit-btn,
  .meta-grid {
    font-family: var(--font-mono);
  }

  .eyebrow,
  .form-kicker {
    color: var(--signal, var(--accent, #ecaa4a));
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    margin-bottom: var(--space-3, 12px);
  }

  .wordmark {
    font-family: var(--font-display);
    font-size: clamp(40px, 8vw, 52px);
    font-weight: 600;
    line-height: 0.95;
    letter-spacing: 0;
    color: var(--text, #e8ecef);
    margin-bottom: var(--space-4, 16px);
  }

  .tagline {
    max-width: 42ch;
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.7);
    color: var(--text-muted, #9aa6ad);
    margin-bottom: var(--space-6, 32px);
  }

  .meta-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 160px));
    gap: var(--space-3, 12px);
  }

  .meta-grid div {
    padding: var(--space-3, 12px);
    background: rgba(159, 177, 188, 0.045);
    border: 1px solid var(--border, rgba(159, 177, 188, 0.2));
  }

  .meta-grid dt {
    color: var(--text-faint, #5f6970);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin-bottom: var(--space-1, 4px);
  }

  .meta-grid dd {
    color: var(--text, #e8ecef);
    font-size: var(--type-chrome-size, 13px);
  }

  .form {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: var(--space-4, 16px);
    width: 100%;
    padding: var(--space-5, 24px);
    background: var(--surface, var(--bg-elev, #101419));
    border: 1px solid var(--border, rgba(159, 177, 188, 0.2));
    border-top-color: var(--rail, rgba(236, 170, 74, 0.58));
  }

  .form-rail {
    position: absolute;
    left: -1px;
    top: -1px;
    right: -1px;
    height: 2px;
    background: var(--signal, var(--accent, #ecaa4a));
  }

  .form-header {
    padding-bottom: var(--space-2, 8px);
    border-bottom: 1px solid var(--border, rgba(159, 177, 188, 0.2));
  }

  .form-copy {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    line-height: 1.55;
    color: var(--text-muted, #9aa6ad);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-1, 4px);
  }

  .field-label {
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: var(--type-chrome-sm-weight, 500);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-faint, #5f6970);
  }

  .password-input {
    width: 100%;
    min-height: 42px;
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    color: var(--text, #e8ecef);
    background-color: var(--bg, #090b0d);
    border: 1px solid var(--border, rgba(159, 177, 188, 0.2));
    border-radius: var(--radius-none, 0);
    padding: var(--space-2, 8px) var(--space-3, 12px);
    outline: none;
    caret-color: var(--signal, var(--accent, #ecaa4a));
    transition:
      border-color var(--dur-fast, 120ms) var(--ease-out),
      background-color var(--dur-fast, 120ms) var(--ease-out);
  }

  .password-input:focus {
    border-color: var(--rail, rgba(236, 170, 74, 0.58));
    background-color: rgba(236, 170, 74, 0.045);
  }

  .remember-label {
    display: flex;
    align-items: center;
    gap: var(--space-2, 8px);
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-muted, #9aa6ad);
    cursor: pointer;
  }

  .remember-label input[type="checkbox"] {
    accent-color: var(--signal, var(--accent, #ecaa4a));
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }

  .error-msg {
    font-size: var(--type-chrome-size, 13px);
    color: var(--signal-danger, #ff6b5f);
    border-left: 2px solid var(--signal-danger, #ff6b5f);
    padding-left: var(--space-2, 8px);
  }

  .submit-btn {
    min-height: 40px;
    align-self: flex-start;
    padding: 0 var(--space-4, 16px);
    color: var(--bg, #090b0d);
    background-color: var(--signal, var(--accent, #ecaa4a));
    border: 1px solid var(--signal, var(--accent, #ecaa4a));
    border-radius: var(--radius-none, 0);
    font-size: var(--type-chrome-size, 13px);
    font-weight: 500;
    cursor: pointer;
    transition:
      opacity var(--dur-fast, 120ms) var(--ease-out),
      background-color var(--dur-fast, 120ms) var(--ease-out);
  }

  .submit-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .submit-btn:not(:disabled):hover {
    opacity: 0.88;
  }

  @keyframes login-reveal {
    from {
      opacity: 0;
      transform: translateY(4px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  @media (max-width: 760px) {
    .onboarding {
      align-items: flex-start;
      padding: var(--space-6, 32px) var(--space-4, 16px);
    }

    .login-console {
      grid-template-columns: 1fr;
      gap: var(--space-6, 32px);
    }

    .signal-block {
      padding-left: var(--space-4, 16px);
    }

    .meta-grid {
      grid-template-columns: 1fr;
    }

    .form {
      padding: var(--space-4, 16px);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .login-console,
    .password-input,
    .submit-btn {
      animation: none;
      transition: none;
    }
  }
</style>
