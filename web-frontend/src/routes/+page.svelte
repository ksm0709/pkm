<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import Onboarding from '$lib/components/Onboarding.svelte';

  let checking = $state(true);

  type VaultEntry = {
    name: string;
    is_default?: boolean;
    active?: boolean;
  };

  function chooseVault(vaults: VaultEntry[], fallback: string | null) {
    return (
      vaults.find((vault) => vault.is_default || vault.active)?.name ||
      (fallback && vaults.some((vault) => vault.name === fallback) ? fallback : null) ||
      vaults[0]?.name ||
      null
    );
  }

  onMount(async () => {
    const token =
      localStorage.getItem('pkm.token') ||
      sessionStorage.getItem('pkm.token');
    const lastVault = localStorage.getItem('pkm.lastVault');

    try {
      const res = await fetch('/api/v1/vaults', { credentials: 'same-origin' });
      if (res.ok) {
        const vaults = await res.json();
        if (Array.isArray(vaults)) {
          const target = chooseVault(vaults, lastVault);
          if (target) {
            await goto(`/${target}/logger`);
            return;
          }
        }
      }
    } catch {
      // Fall through to local fallback or login form.
    }

    if (token && lastVault) {
      goto(`/${lastVault}/logger`);
      return;
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
