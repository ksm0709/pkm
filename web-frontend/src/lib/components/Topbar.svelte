<script lang="ts">
  interface Props {
    vaultName?: string;
    vimMode?: string;
  }

  let { vaultName = '', vimMode = 'NORMAL' }: Props = $props();
</script>

<header class="topbar">
  <div class="topbar-left">
    {#if vaultName}
      <span class="vault-name">{vaultName}</span>
    {:else}
      <span class="vault-name faint">pkm</span>
    {/if}
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
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: var(--topbar-height, 44px);
    padding: 0 var(--space-4, 16px);
    background-color: var(--bg);
    border-bottom: 1px solid var(--border);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    line-height: var(--type-chrome-lh, 1.20);
    font-weight: var(--type-chrome-weight, 400);
    /* No box-shadow */
  }

  .topbar-left,
  .topbar-right {
    display: flex;
    align-items: center;
    gap: var(--space-3, 12px);
  }

  .vault-name {
    color: var(--text);
  }

  .vault-name.faint {
    color: var(--text-faint);
  }

  .vim-mode {
    color: var(--text-muted);
  }

  .kbd-hint {
    color: var(--text-faint);
  }
</style>
