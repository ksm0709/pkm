<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import Topbar from "$lib/components/Topbar.svelte";
  import AppNavDrawer from "$lib/components/AppNavDrawer.svelte";
  import CmdK from "$lib/components/CmdK.svelte";
  import WikilinkPreview from "$lib/components/WikilinkPreview.svelte";
  import { loadConfigs } from "$lib/configs/client";
  import {
    DEFAULT_WINDOW_PADDING,
    applyWindowLayoutVars,
    clearWindowLayoutVars,
    parseWindowPadding,
    windowLayoutVars,
  } from "$lib/layout/window-layout";
  import type { Snippet } from "svelte";

  interface Props {
    children: Snippet;
  }

  let { children }: Props = $props();

  let vaultName = $derived($page.params.vault ?? "");
  let pageName = $derived(pageNameFromPath($page.url.pathname, vaultName));
  let drawerOpen = $state(false);
  let commandPaletteOpenToken = $state(0);
  let vaultContentEl = $state<HTMLDivElement | null>(null);
  let contentInlineSize = $state(0);
  let windowPadding = $state(DEFAULT_WINDOW_PADDING);
  const drawerStorageKey = "pkm.appNavOpen";
  let pendingKey = "";
  let pendingTimer: ReturnType<typeof setTimeout> | null = null;
  let layoutLoadSequence = 0;
  let resizeObserver: ResizeObserver | null = null;

  onMount(() => {
    try {
      drawerOpen = localStorage.getItem(drawerStorageKey) === "true";
    } catch {
      // ignore — SSR or private-browsing restriction
    }

    // Install global navigation hook used by vim mappings (F4-5).
    // Other actions are stubs here; F4-2/F4-4/F3 wire them in later.
    (window as any).__pkmNav = {
      gotoDaily: () =>
        goto(`/${vaultName}/notes/${new Date().toISOString().slice(0, 10)}`),
      gotoNote: (id: string) => goto(`/${vaultName}/notes/${id}`),
      nextNeighbor: () => false,
      prevNeighbor: () => false,
      followAtCursor: () => false,
      openExternal: () => false,
      openPalette: () => openCommandPalette(),
    };

    window.addEventListener("keydown", handleKeydown);
    window.addEventListener("pkm:config-change", handleConfigChange);

    measureVaultContent();
    if (typeof ResizeObserver !== "undefined" && vaultContentEl) {
      resizeObserver = new ResizeObserver((entries) => {
        contentInlineSize =
          entries[0]?.contentRect.width ?? vaultContentEl?.clientWidth ?? 0;
      });
      resizeObserver.observe(vaultContentEl);
    } else {
      window.addEventListener("resize", measureVaultContent);
    }
  });

  onDestroy(() => {
    if (typeof window !== "undefined") {
      window.removeEventListener("keydown", handleKeydown);
      window.removeEventListener("pkm:config-change", handleConfigChange);
      window.removeEventListener("resize", measureVaultContent);
      resizeObserver?.disconnect();
      resizeObserver = null;
      try {
        delete (window as any).__pkmNav;
      } catch {
        (window as any).__pkmNav = undefined;
      }
      if (pendingTimer) {
        clearTimeout(pendingTimer);
        pendingTimer = null;
      }
    }
    if (typeof document !== "undefined") {
      clearWindowLayoutVars(document.documentElement);
    }
  });

  $effect(() => {
    applyWindowLayoutVars(
      document.documentElement,
      windowLayoutVars({ contentInlineSize, paddingPx: windowPadding }),
    );
  });

  $effect(() => {
    const vault = vaultName;
    if (!vault) return;
    void refreshWindowPadding(vault);
  });

  function toggleDrawer() {
    drawerOpen = !drawerOpen;
    try {
      localStorage.setItem(drawerStorageKey, String(drawerOpen));
    } catch {
      // ignore
    }
  }

  function closeDrawer() {
    drawerOpen = false;
    try {
      localStorage.setItem(drawerStorageKey, "false");
    } catch {
      // ignore
    }
  }

  function openCommandPalette() {
    commandPaletteOpenToken += 1;
    return true;
  }

  async function refreshWindowPadding(vault: string) {
    const sequence = ++layoutLoadSequence;
    try {
      const configs = await loadConfigs(vault);
      if (sequence !== layoutLoadSequence || vaultName !== vault) return;
      const setting = configs.settings?.find(
        (item) => item.key === "web-window-padding",
      );
      windowPadding = parseWindowPadding(
        setting?.value ?? setting?.default_value,
      );
    } catch {
      if (sequence === layoutLoadSequence && vaultName === vault) {
        windowPadding = DEFAULT_WINDOW_PADDING;
      }
    }
  }

  function measureVaultContent() {
    contentInlineSize =
      vaultContentEl?.getBoundingClientRect().width ??
      vaultContentEl?.clientWidth ??
      0;
  }

  function handleConfigChange(event: Event) {
    const detail = (event as CustomEvent<{ key?: string; value?: unknown }>)
      .detail;
    if (detail?.key !== "web-window-padding") return;
    windowPadding = parseWindowPadding(detail.value);
  }

  function pageNameFromPath(pathname: string, vault: string) {
    if (!vault) return "pkm";
    const parts = pathname.split("/").filter(Boolean);
    if (parts[0] !== vault) return "home";
    if (parts.length === 1) return "notes";
    if (parts[1] === "notes" && parts[2]) return decodeURIComponent(parts[2]);
    if (parts[1] === "daily") return "daily";
    if (parts[1] === "logger") return "logger";
    if (parts[1] === "workflows" && parts[2])
      return `workflow:${decodeURIComponent(parts[2])}`;
    if (parts[1] === "workflows") return "workflows";
    if (parts[1] === "ask") return "ask";
    return parts[1] || "home";
  }

  function handleKeydown(event: KeyboardEvent) {
    const key = event.key.toLowerCase();
    const target = event.target;
    const isTypingTarget =
      target instanceof HTMLElement &&
      (target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable);

    if (!isTypingTarget && pendingKey === "g") {
      pendingKey = "";
      if (pendingTimer) {
        clearTimeout(pendingTimer);
        pendingTimer = null;
      }
      if (key === "d") {
        event.preventDefault();
        goto(`/${vaultName}/notes/${new Date().toISOString().slice(0, 10)}`);
        return;
      }
    }

    if (!isTypingTarget && key === "g") {
      pendingKey = "g";
      if (pendingTimer) clearTimeout(pendingTimer);
      pendingTimer = setTimeout(() => {
        pendingKey = "";
        pendingTimer = null;
      }, 800);
      return;
    }

    if (
      (event.metaKey || event.ctrlKey) &&
      (key === "b" || event.code === "KeyB")
    ) {
      event.preventDefault();
      toggleDrawer();
    }

    if (
      event.key === "Escape" &&
      document.querySelector('[role="dialog"][aria-label="Command palette"]')
    ) {
      return;
    }

    if (event.key === "Escape" && drawerOpen) {
      closeDrawer();
    }
  }
</script>

<Topbar
  {vaultName}
  {pageName}
  {drawerOpen}
  {toggleDrawer}
  {openCommandPalette}
/>

<div class="vault-shell" class:drawer-open={drawerOpen}>
  <AppNavDrawer
    {vaultName}
    open={drawerOpen}
    {openCommandPalette}
    {closeDrawer}
  />
  {#if drawerOpen}
    <button
      class="drawer-scrim"
      type="button"
      aria-label="Close navigation drawer"
      onclick={closeDrawer}
    ></button>
  {/if}
  <div class="vault-content" bind:this={vaultContentEl}>
    {@render children()}
  </div>
</div>

<CmdK {vaultName} openToken={commandPaletteOpenToken} />

<WikilinkPreview vault={vaultName} />

<style>
  .vault-shell {
    position: relative;
    display: flex;
    flex-direction: row;
    height: calc(100vh - var(--topbar-height, 48px));
    height: calc(100svh - var(--topbar-height, 48px));
    height: calc(100dvh - var(--topbar-height, 48px));
    min-height: 0;
    overflow: hidden;
    background: var(--bg);
    animation: shell-reveal var(--dur-base, 200ms) var(--ease-out) both;
  }

  .vault-content {
    flex: 1;
    min-width: 0;
    min-height: 0;
    overflow-x: hidden;
    overflow-y: auto;
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
      height: calc(100vh - var(--topbar-height, 48px));
      height: calc(100svh - var(--topbar-height, 48px));
      height: calc(100dvh - var(--topbar-height, 48px));
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
