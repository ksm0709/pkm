<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import Onboarding from '$lib/components/Onboarding.svelte';

  let checking = $state(true);

  onMount(async () => {
    const token =
      localStorage.getItem('pkm.token') ||
      sessionStorage.getItem('pkm.token');

    if (token) {
      // Token present — redirect to last vault or /[vault] placeholder
      const lastVault = localStorage.getItem('pkm.lastVault');
      if (lastVault) {
        goto(`/${lastVault}`);
        return;
      }
    } else {
      try {
        const res = await fetch('/api/v1/vaults', { credentials: 'same-origin' });
        if (res.ok) {
          const vaults = await res.json();
          const lastVault = localStorage.getItem('pkm.lastVault');
          if (lastVault) {
            await goto(`/${lastVault}`);
            return;
          }
          if (Array.isArray(vaults) && vaults.length > 0) {
            await goto(`/${vaults[0].name}`);
            return;
          }
        }
      } catch {
        // Fall through to login form.
      }
    }
    checking = false;
  });
</script>

<svelte:head>
  <title>pkm</title>
</svelte:head>

{#if !checking}
  <Onboarding />
{/if}
