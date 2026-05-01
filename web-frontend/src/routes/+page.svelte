<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import Onboarding from '$lib/components/Onboarding.svelte';

  let hasToken = $state(false);
  let checking = $state(true);

  onMount(() => {
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
      // No last vault yet; show onboarding to pick vault after auth
      hasToken = false;
    } else {
      hasToken = false;
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
