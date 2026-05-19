<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import Onboarding from "$lib/components/Onboarding.svelte";
  import { readRememberedVault } from "$lib/vault/remembered-vault";

  let checking = $state(true);

  type VaultEntry =
    | string
    | {
        name: string;
        is_default?: boolean;
        active?: boolean;
      };

  function vaultName(vault: VaultEntry | undefined) {
    if (!vault) return null;
    return typeof vault === "string" ? vault : vault.name;
  }

  function chooseVault(vaults: VaultEntry[], fallback: string | null) {
    return (
      (fallback && vaults.some((vault) => vaultName(vault) === fallback)
        ? fallback
        : null) ||
      vaultName(
        vaults.find(
          (vault) =>
            typeof vault !== "string" && (vault.is_default || vault.active),
        ) ?? vaults[0],
      ) ||
      null
    );
  }

  onMount(async () => {
    const token =
      localStorage.getItem("pkm.token") || sessionStorage.getItem("pkm.token");
    const lastVault = readRememberedVault();

    try {
      const res = await fetch("/api/v1/vaults", { credentials: "same-origin" });
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
