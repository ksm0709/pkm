<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import Topbar from '$lib/components/Topbar.svelte';
  import FileTreeDrawer from '$lib/components/FileTreeDrawer.svelte';
  import CmdK from '$lib/components/CmdK.svelte';
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
