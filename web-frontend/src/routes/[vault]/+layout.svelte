<script lang="ts">
  import { page } from '$app/stores';
  import Topbar from '$lib/components/Topbar.svelte';
  import type { Snippet } from 'svelte';

  interface Props {
    children: Snippet;
  }

  let { children }: Props = $props();

  let vaultName = $derived($page.params.vault ?? '');
</script>

<Topbar {vaultName} />

<div class="vault-shell">
  {@render children()}
</div>

<style>
  .vault-shell {
    min-height: calc(100vh - var(--topbar-height, 44px));
  }
</style>
