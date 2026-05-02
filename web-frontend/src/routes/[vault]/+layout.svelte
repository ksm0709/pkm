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

  function handleKeydown(event: KeyboardEvent) {
    if ((event.metaKey || event.ctrlKey) && event.key === 'b') {
      event.preventDefault();
      toggleDrawer();
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<Topbar {vaultName} />

<div class="vault-shell">
  <FileTreeDrawer {vaultName} open={drawerOpen} />
  <div class="vault-content">
    {@render children()}
  </div>
</div>

<CmdK {vaultName} />

<WikilinkPreview vault={vaultName} />

<style>
  .vault-shell {
    display: flex;
    flex-direction: row;
    min-height: calc(100vh - var(--topbar-height, 44px));
  }

  /* Content area takes remaining width; min-width:0 prevents flex overflow */
  .vault-content {
    flex: 1;
    min-width: 0;
    overflow: hidden;
  }
</style>
