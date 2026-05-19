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
    graphKeyNav,
    noteHref,
    type NavigationTarget,
  } from "$lib/navigation/graph-keynav.svelte";
  import {
    DEFAULT_WINDOW_PADDING,
    applyWindowLayoutVars,
    clearWindowLayoutVars,
    parseWindowPadding,
    windowLayoutVars,
  } from "$lib/layout/window-layout";
  import { rememberVault } from "$lib/vault/remembered-vault";
  import type { Snippet } from "svelte";

  interface Props {
    children: Snippet;
  }

  type NavAction =
    | "gotoDaily"
    | "nextNeighbor"
    | "prevNeighbor"
    | "back"
    | "followAtCursor"
    | "openExternal"
    | "openPalette"
    | "openNoteSearch";

  interface KeyHintAction {
    key: string;
    description: string;
    navAction?: NavAction;
    run?: () => boolean;
  }

  const KEY_HINT_TIMEOUT_MS = 1200;
  const leaderKeyHintActions: Record<string, KeyHintAction[]> = {
    " ": [
      {
        key: "k",
        description: "Open command palette",
        navAction: "openPalette",
      },
      {
        key: "/",
        description: "Jump to note",
        navAction: "openNoteSearch",
      },
    ],
  };
  const keyHintPrefixes = new Set(["g", " "]);

  function gotoKeyHintActions(): KeyHintAction[] {
    const actions: KeyHintAction[] = [
      { key: "d", description: "Open daily note", navAction: "gotoDaily" },
    ];
    if (graphKeyNav.hasSemanticNeighbors) {
      actions.push(
        {
          key: "n",
          description: "Next semantic neighbor",
          navAction: "nextNeighbor",
        },
        {
          key: "p",
          description: "Previous semantic neighbor",
          navAction: "prevNeighbor",
        },
      );
      for (const action of graphKeyNav.semanticRankActions) {
        actions.push({
          key: action.key,
          description: action.description,
          run: () =>
            navigateGraphTarget(
              graphKeyNav.navigateToSemanticRank(action.rank),
            ),
        });
      }
    }
    if (graphKeyNav.canGoBack) {
      actions.push({
        key: "b",
        description: "Back",
        navAction: "back",
      });
    }
    return actions;
  }

  function keyHintActionsFor(prefix: string) {
    if (prefix === "g") return gotoKeyHintActions();
    return leaderKeyHintActions[prefix] ?? [];
  }

  function navigateGraphTarget(target: NavigationTarget | null) {
    if (!target) return false;
    void goto(noteHref(target));
    return true;
  }

  function gotoDailyNote() {
    graphKeyNav.pushCurrent();
    return goto(`/${vaultName}/notes/${new Date().toISOString().slice(0, 10)}`);
  }

  let { children }: Props = $props();

  let vaultName = $derived($page.params.vault ?? "");
  let pageName = $derived(pageNameFromPath($page.url.pathname, vaultName));
  let drawerOpen = $state(false);
  let commandPaletteOpenToken = $state(0);
  let noteSearchOpenToken = $state(0);
  let vaultContentEl = $state<HTMLDivElement | null>(null);
  let contentInlineSize = $state(0);
  let windowPadding = $state(DEFAULT_WINDOW_PADDING);
  const drawerStorageKey = "pkm.appNavOpen";
  let pendingKey = $state("");
  let pendingTimer: ReturnType<typeof setTimeout> | null = null;
  let layoutLoadSequence = 0;
  let resizeObserver: ResizeObserver | null = null;
  let activeKeyHints = $derived.by(() => keyHintActionsFor(pendingKey));
  let activeKeyHintLabel = $derived(pendingKey === " " ? "Space" : pendingKey);

  onMount(() => {
    try {
      drawerOpen = localStorage.getItem(drawerStorageKey) === "true";
    } catch {
      // ignore — SSR or private-browsing restriction
    }

    // Install global navigation hook used by vim mappings (F4-5).
    (window as any).__pkmNav = {
      gotoDaily: () => gotoDailyNote(),
      gotoNote: (id: string) => goto(noteHref({ vaultName, noteId: id })),
      nextNeighbor: () =>
        navigateGraphTarget(graphKeyNav.navigateNextSemantic()),
      prevNeighbor: () =>
        navigateGraphTarget(graphKeyNav.navigatePreviousSemantic()),
      back: () => navigateGraphTarget(graphKeyNav.popNavigationStack()),
      followAtCursor: () => false,
      openExternal: () => false,
      openPalette: () => openCommandPalette(),
      openNoteSearch: () => openNoteSearch(),
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
      clearPendingKeyHint();
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
    rememberVault(vault);
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

  function openNoteSearch() {
    noteSearchOpenToken += 1;
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

  function isTypingTarget(target: EventTarget | null) {
    if (!(target instanceof HTMLElement)) return false;
    return (
      target.tagName === "INPUT" ||
      target.tagName === "TEXTAREA" ||
      target.tagName === "SELECT" ||
      target.isContentEditable ||
      Boolean(target.closest(".cm-editor"))
    );
  }

  function hasOpenDialog() {
    return Boolean(
      document.querySelector('[role="dialog"], [role="alertdialog"]'),
    );
  }

  function clearPendingKeyHint() {
    pendingKey = "";
    if (pendingTimer) {
      clearTimeout(pendingTimer);
      pendingTimer = null;
    }
  }

  function openPendingKeyHint(prefix: string) {
    pendingKey = prefix;
    if (pendingTimer) clearTimeout(pendingTimer);
    pendingTimer = setTimeout(() => {
      clearPendingKeyHint();
    }, KEY_HINT_TIMEOUT_MS);
  }

  function runPendingKeyAction(key: string) {
    const action = activeKeyHints.find((item) => item.key === key);
    clearPendingKeyHint();
    if (!action) return false;
    if (action.run) return action.run();
    const nav = (window as any).__pkmNav as
      | Partial<Record<NavAction, () => unknown>>
      | undefined;
    const fn = nav?.[action.navAction];
    if (typeof fn !== "function") return false;
    fn();
    return true;
  }

  function handleKeydown(event: KeyboardEvent) {
    const key = event.key.toLowerCase();
    const isTyping = isTypingTarget(event.target);

    if (
      !isTyping &&
      !hasOpenDialog() &&
      event.ctrlKey &&
      !event.metaKey &&
      !event.altKey &&
      (key === "o" || event.code === "KeyO")
    ) {
      if (navigateGraphTarget(graphKeyNav.popNavigationStack())) {
        event.preventDefault();
      }
      return;
    }

    if (!isTyping && pendingKey) {
      if (key === "escape") {
        event.preventDefault();
        clearPendingKeyHint();
        return;
      }
      if (runPendingKeyAction(key)) {
        event.preventDefault();
      }
      return;
    }

    if (!isTyping && keyHintPrefixes.has(key) && !hasOpenDialog()) {
      openPendingKeyHint(key);
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

<CmdK
  {vaultName}
  openToken={commandPaletteOpenToken}
  searchOpenToken={noteSearchOpenToken}
/>

{#if activeKeyHints.length > 0}
  <aside
    class="key-hint"
    role="status"
    aria-label="Key sequence hints"
    data-key-hint
  >
    <div class="key-hint-prefix">
      <kbd>{activeKeyHintLabel}</kbd>
    </div>
    <div class="key-hint-list">
      {#each activeKeyHints as action}
        <div class="key-hint-row">
          <kbd>{action.key}</kbd>
          <span>{action.description}</span>
        </div>
      {/each}
    </div>
  </aside>
{/if}

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

  .key-hint {
    position: fixed;
    right: max(16px, var(--window-padding, 24px));
    bottom: 16px;
    z-index: 120;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: var(--space-3, 12px);
    max-width: min(320px, calc(100vw - 32px));
    padding: 10px 12px;
    color: var(--text);
    background: color-mix(in srgb, var(--bg-elev) 94%, transparent);
    border: 1px solid var(--border);
    border-radius: 2px;
    box-shadow: var(--shadow-lg);
  }

  .key-hint-prefix {
    display: flex;
    align-items: flex-start;
    padding-top: 1px;
  }

  .key-hint-list {
    display: grid;
    gap: 6px;
    min-width: 0;
  }

  .key-hint-row {
    display: grid;
    grid-template-columns: 24px minmax(0, 1fr);
    align-items: center;
    gap: 8px;
    min-height: 22px;
    font-size: var(--type-caption-size, 12px);
    line-height: 1.35;
  }

  .key-hint kbd {
    display: inline-grid;
    min-width: 22px;
    height: 22px;
    place-items: center;
    padding: 0 5px;
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 700;
    line-height: 1;
    color: var(--accent);
    background: var(--surface-raised, var(--bg));
    border: 1px solid color-mix(in srgb, var(--accent) 38%, var(--border));
    border-radius: 2px;
  }

  .key-hint-prefix kbd {
    min-width: 44px;
    color: var(--bg);
    background: var(--accent);
    border-color: var(--accent);
  }

  .key-hint-row span {
    min-width: 0;
    overflow: hidden;
    color: var(--text-muted);
    text-overflow: ellipsis;
    white-space: nowrap;
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
