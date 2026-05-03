<script lang="ts">
  interface Props {
    vaultName?: string;
    vimMode?: string;
    drawerOpen?: boolean;
    onToggleDrawer?: () => void;
  }

  let {
    vaultName = '',
    vimMode = 'NORMAL',
    drawerOpen = false,
    onToggleDrawer = () => {}
  }: Props = $props();
</script>

<header class="topbar" aria-label="Vault status rail">
  <div class="topbar-left">
    <button
      class="drawer-toggle"
      type="button"
      aria-label={drawerOpen ? 'Close file drawer' : 'Open file drawer'}
      aria-pressed={drawerOpen}
      onclick={onToggleDrawer}
    >
      <span class="toggle-mark" aria-hidden="true"></span>
      <span class="toggle-text">FILES</span>
    </button>

    <div class="station" aria-label="Active vault">
      <span class="station-kicker">station</span>
      {#if vaultName}
        <span class="vault-name">{vaultName}</span>
      {:else}
        <span class="vault-name faint">pkm</span>
      {/if}
    </div>
  </div>

  <div class="topbar-center" aria-hidden="true">
    <span class="rail-line"></span>
    <span class="mode-label">signal desk</span>
    <span class="rail-line"></span>
  </div>

  <div class="topbar-right">
    <span class="vim-mode">vim:{vimMode}</span>
    <span class="kbd-hint">⌘K</span>
  </div>
</header>

<style>
  .topbar {
    position: sticky;
    top: 0;
    z-index: 100;
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(120px, 0.75fr) minmax(0, 1fr);
    align-items: center;
    height: 48px;
    padding: 0 var(--space-4, 16px);
    background:
      linear-gradient(90deg, rgba(236, 170, 74, 0.08), transparent 34%, transparent 66%, rgba(112, 199, 216, 0.06)),
      var(--bg, #090b0d);
    border-bottom: 1px solid var(--border, rgba(159, 177, 188, 0.20));
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    line-height: var(--type-chrome-lh, 1.20);
    font-weight: var(--type-chrome-weight, 400);
  }

  .topbar::before {
    content: '';
    position: absolute;
    left: 0;
    bottom: -1px;
    width: min(33vw, 420px);
    height: 1px;
    background: var(--rail, rgba(236, 170, 74, 0.58));
    pointer-events: none;
  }

  .topbar-left,
  .topbar-right,
  .topbar-center {
    min-width: 0;
    display: flex;
    align-items: center;
  }

  .topbar-left {
    justify-content: flex-start;
    gap: var(--space-3, 12px);
  }

  .topbar-center {
    justify-content: center;
    gap: var(--space-2, 8px);
    color: var(--text-faint, #5f6970);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--type-chrome-sm-size, 11px);
    white-space: nowrap;
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
    background: rgba(159, 177, 188, 0.045);
    border: 1px solid var(--border, rgba(159, 177, 188, 0.20));
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
  .drawer-toggle[aria-pressed='true'] {
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

  .drawer-toggle[aria-pressed='true'] .toggle-mark {
    transform: rotate(-45deg);
  }

  .station {
    min-width: 0;
    display: grid;
    gap: 2px;
  }

  .station-kicker {
    color: var(--text-faint, #5f6970);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    white-space: nowrap;
  }

  .vault-name {
    min-width: 0;
    color: var(--text, #e8ecef);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .vault-name.faint {
    color: var(--text-faint, #5f6970);
  }

  .rail-line {
    display: block;
    width: min(9vw, 96px);
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--border, rgba(159, 177, 188, 0.20)), transparent);
  }

  .vim-mode,
  .kbd-hint {
    display: inline-flex;
    align-items: center;
    height: 28px;
    max-width: 42vw;
    padding: 0 var(--space-2, 8px);
    border: 1px solid var(--border, rgba(159, 177, 188, 0.20));
    color: var(--text-muted, #9aa6ad);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .kbd-hint {
    color: var(--signal, var(--accent, #ecaa4a));
    border-color: rgba(236, 170, 74, 0.32);
    transition:
      border-color var(--dur-fast, 120ms) var(--ease-out),
      background-color var(--dur-fast, 120ms) var(--ease-out);
  }

  .kbd-hint:hover {
    background: var(--accent-bg, rgba(236, 170, 74, 0.12));
    border-color: var(--rail, rgba(236, 170, 74, 0.58));
  }

  @media (max-width: 760px) {
    .topbar {
      grid-template-columns: minmax(0, 1fr) auto;
      height: 48px;
      padding: 0 var(--space-3, 12px);
      column-gap: var(--space-2, 8px);
    }

    .topbar-center {
      display: none;
    }

    .topbar-right {
      gap: var(--space-1, 4px);
    }

    .vim-mode {
      display: none;
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
    .kbd-hint {
      transition: none;
    }
  }
</style>
