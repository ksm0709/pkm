<script lang="ts">
  import { goto } from "$app/navigation";

  interface Props {
    vaultName?: string;
    pageName?: string;
    drawerOpen?: boolean;
    toggleDrawer?: () => void;
    openCommandPalette?: () => void;
  }

  let {
    vaultName = "",
    pageName = "home",
    drawerOpen = false,
    toggleDrawer = () => {},
    openCommandPalette = () => {},
  }: Props = $props();

  function openVaultLogger() {
    if (!vaultName) return;
    void goto(`/${vaultName}/logger`);
  }
</script>

<header class="topbar" aria-label="Vault status rail">
  <div class="topbar-left">
    <button
      class="drawer-toggle"
      type="button"
      aria-label={drawerOpen
        ? "Close navigation drawer"
        : "Open navigation drawer"}
      aria-pressed={drawerOpen}
      onclick={toggleDrawer}
    >
      <span class="toggle-mark" aria-hidden="true"></span>
      <span class="toggle-text">NAV</span>
    </button>

    <button
      class="breadcrumb"
      type="button"
      aria-label="Open vault logger"
      disabled={!vaultName}
      onclick={openVaultLogger}
    >
      {#if vaultName}
        <span class="vault-name">{vaultName}</span>
        <span class="breadcrumb-separator" aria-hidden="true">&gt;</span>
        <span class="page-name">{pageName}</span>
      {:else}
        <span class="vault-name faint">pkm</span>
      {/if}
    </button>
  </div>

  <div class="topbar-right">
    <button
      class="command-button"
      type="button"
      aria-label="Open command palette"
      onclick={openCommandPalette}
    >
      ⌘K
    </button>
  </div>
</header>

<style>
  .topbar {
    position: sticky;
    top: 0;
    z-index: 100;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    height: var(--topbar-height, 48px);
    padding: 0 var(--space-4, 16px);
    background: var(--bg, #090b0d);
    border-bottom: 1px solid var(--border, rgba(159, 177, 188, 0.2));
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    line-height: var(--type-chrome-lh, 1.2);
    font-weight: var(--type-chrome-weight, 400);
  }

  .topbar::before {
    content: "";
    position: absolute;
    left: 0;
    bottom: -1px;
    width: min(33vw, 420px);
    height: 1px;
    background: var(--rail, rgba(236, 170, 74, 0.58));
    pointer-events: none;
  }

  .topbar-left,
  .topbar-right {
    min-width: 0;
    display: flex;
    align-items: center;
  }

  .topbar-left {
    justify-content: flex-start;
    gap: var(--space-3, 12px);
  }

  .topbar-right {
    justify-content: flex-end;
    gap: var(--space-2, 8px);
  }

  .drawer-toggle {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: var(--space-2, 8px);
    height: 30px;
    flex: 0 0 auto;
    padding: 0 var(--space-3, 12px) 0 10px;
    color: var(--text-muted, #9aa6ad);
    background: color-mix(in srgb, var(--text-muted, #9aa6ad) 8%, transparent);
    border: 1px solid var(--border, rgba(159, 177, 188, 0.2));
    border-left-color: var(--rail, rgba(236, 170, 74, 0.58));
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    line-height: 1;
    letter-spacing: 0.12em;
    transition:
      color var(--dur-fast, 120ms) var(--ease-out),
      border-color var(--dur-fast, 120ms) var(--ease-out),
      background-color var(--dur-fast, 120ms) var(--ease-out);
  }

  .drawer-toggle:hover,
  .drawer-toggle:focus-visible,
  .drawer-toggle[aria-pressed="true"] {
    color: var(--text, #e8ecef);
    background: var(--accent-bg, rgba(236, 170, 74, 0.12));
    border-color: var(--rail, rgba(236, 170, 74, 0.58));
    outline: none;
  }

  .toggle-mark {
    width: 10px;
    height: 10px;
    border-left: 2px solid var(--signal, var(--accent, #ecaa4a));
    border-top: 2px solid var(--signal, var(--accent, #ecaa4a));
    transform: rotate(135deg);
    transition: transform var(--dur-base, 200ms) var(--ease-out);
  }

  .drawer-toggle[aria-pressed="true"] .toggle-mark {
    transform: rotate(-45deg);
  }

  .breadcrumb {
    min-width: 0;
    display: flex;
    align-items: center;
    gap: var(--space-2, 8px);
    white-space: nowrap;
    overflow: hidden;
    padding: 0;
    border: 0;
    background: transparent;
    font: inherit;
    cursor: pointer;
  }

  .breadcrumb:disabled {
    cursor: default;
  }

  .breadcrumb:not(:disabled):hover .vault-name,
  .breadcrumb:not(:disabled):focus-visible .vault-name,
  .breadcrumb:not(:disabled):hover .page-name,
  .breadcrumb:not(:disabled):focus-visible .page-name {
    color: var(--signal, var(--accent, #ecaa4a));
  }

  .breadcrumb:focus-visible {
    outline: 1px solid var(--rail, rgba(236, 170, 74, 0.58));
    outline-offset: 3px;
  }

  .breadcrumb-separator {
    flex: 0 0 auto;
    color: var(--text-faint, #5f6970);
    white-space: nowrap;
  }

  .vault-name,
  .page-name {
    min-width: 0;
    color: var(--text, #e8ecef);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .vault-name.faint {
    color: var(--text-faint, #5f6970);
  }

  .page-name {
    color: var(--text-muted, #9aa6ad);
  }

  .command-button {
    display: inline-flex;
    align-items: center;
    height: 28px;
    max-width: 42vw;
    padding: 0 var(--space-2, 8px);
    border: 1px solid var(--border, rgba(159, 177, 188, 0.2));
    color: var(--text-muted, #9aa6ad);
    background: transparent;
    font: inherit;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .command-button {
    color: var(--signal, var(--accent, #ecaa4a));
    border-color: color-mix(
      in srgb,
      var(--signal, var(--accent, #ecaa4a)) 42%,
      transparent
    );
    cursor: pointer;
    transition:
      border-color var(--dur-fast, 120ms) var(--ease-out),
      background-color var(--dur-fast, 120ms) var(--ease-out);
  }

  .command-button:hover,
  .command-button:focus-visible {
    background: var(--accent-bg, rgba(236, 170, 74, 0.12));
    border-color: var(--rail, rgba(236, 170, 74, 0.58));
    outline: none;
  }

  @media (max-width: 760px) {
    .topbar {
      grid-template-columns: minmax(0, 1fr) auto;
      height: 48px;
      padding: 0 var(--space-3, 12px);
      column-gap: var(--space-2, 8px);
    }

    .topbar-right {
      gap: var(--space-1, 4px);
    }

    .toggle-text {
      display: none;
    }

    .drawer-toggle {
      width: 34px;
      padding: 0;
      justify-content: center;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .drawer-toggle,
    .toggle-mark,
    .command-button {
      transition: none;
    }
  }
</style>
