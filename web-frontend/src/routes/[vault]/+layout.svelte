<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import Topbar from '$lib/components/Topbar.svelte';
  import FileTreeDrawer from '$lib/components/FileTreeDrawer.svelte';
  import CmdK from '$lib/components/CmdK.svelte';
  import WikilinkPreview from '$lib/components/WikilinkPreview.svelte';
  import type { Snippet } from 'svelte';

  interface Props {
    children: Snippet;
  }

  let { children }: Props = $props();

  let vaultName = $derived($page.params.vault ?? '');
  let drawerOpen = $state(false);

  onMount(() => {
    try {
      drawerOpen = localStorage.getItem('pkm.fileTreeOpen') === 'true';
    } catch {
      // ignore — SSR or private-browsing restriction
    }

    // Install global navigation hook used by vim mappings (F4-5).
    // Other actions are stubs here; F4-2/F4-4/F3 wire them in later.
    (window as any).__pkmNav = {
      gotoDaily: () => goto(`/${vaultName}/daily/today`),
      gotoNote: (id: string) => goto(`/${vaultName}/notes/${id}`),
      nextNeighbor: () => false,
      prevNeighbor: () => false,
      followAtCursor: () => false,
      openExternal: () => false,
      openPalette: () => false
    };
  });

  onDestroy(() => {
    if (typeof window !== 'undefined') {
      try {
        delete (window as any).__pkmNav;
      } catch {
        (window as any).__pkmNav = undefined;
      }
    }
  });

  function toggleDrawer() {
    drawerOpen = !drawerOpen;
    try {
      localStorage.setItem('pkm.fileTreeOpen', String(drawerOpen));
    } catch {
      // ignore
    }
  }

  function closeDrawer() {
    drawerOpen = false;
    try {
      localStorage.setItem('pkm.fileTreeOpen', 'false');
    } catch {
      // ignore
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if ((event.metaKey || event.ctrlKey) && event.key === 'b') {
      event.preventDefault();
      toggleDrawer();
    }

    if (event.key === 'Escape' && drawerOpen) {
      closeDrawer();
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<Topbar {vaultName} drawerOpen={drawerOpen} onToggleDrawer={toggleDrawer} />

<div class="vault-shell" class:drawer-open={drawerOpen}>
  <div class="shell-rail" aria-hidden="true"></div>
  <FileTreeDrawer {vaultName} open={drawerOpen} />
  {#if drawerOpen}
    <button class="drawer-scrim" type="button" aria-label="Close file drawer" onclick={closeDrawer}></button>
  {/if}
  <div class="vault-content">
    {@render children()}
  </div>
</div>

<CmdK {vaultName} />

<WikilinkPreview vault={vaultName} />

<style>
  .vault-shell {
    --bg: #090b0d;
    --bg-elev: #101419;
    --surface: #101419;
    --text: #e8ecef;
    --text-muted: #9aa6ad;
    --text-faint: #5f6970;
    --border: rgba(159, 177, 188, 0.20);
    --accent: #ecaa4a;
    --accent-bg: rgba(236, 170, 74, 0.12);
    --signal: #ecaa4a;
    --rail: rgba(236, 170, 74, 0.58);
    position: relative;
    display: flex;
    flex-direction: row;
    min-height: calc(100vh - 48px);
    background:
      linear-gradient(90deg, rgba(236, 170, 74, 0.08) 0 1px, transparent 1px 100%) left top / 24px 100% no-repeat,
      var(--bg, #090b0d);
    animation: shell-reveal var(--dur-base, 200ms) var(--ease-out) both;
  }

  .shell-rail {
    flex: 0 0 12px;
    border-right: 1px solid var(--border, rgba(159, 177, 188, 0.20));
    background:
      linear-gradient(180deg, var(--rail, rgba(236, 170, 74, 0.58)), transparent 180px),
      rgba(159, 177, 188, 0.025);
  }

  .vault-content {
    flex: 1;
    min-width: 0;
    overflow: hidden;
  }

  .drawer-scrim {
    display: none;
  }

  @keyframes shell-reveal {
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
    .vault-shell {
      min-height: calc(100vh - 48px);
    }

    .shell-rail {
      flex-basis: 8px;
    }

    .drawer-scrim {
      position: fixed;
      inset: 48px 0 0 0;
      z-index: 80;
      display: block;
      background: rgba(9, 11, 13, 0.58);
      border: 0;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .vault-shell {
      animation: none;
    }
  }
</style>
