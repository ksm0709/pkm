<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';

  interface Props {
    vaultName: string;
    open?: boolean;
    openCommandPalette?: () => void;
    closeDrawer?: () => void;
  }

  type NavItem = {
    id: string;
    label: string;
    meta: string;
    href?: string;
    action?: () => void;
    disabled?: boolean;
  };

  const props = $props<Props>();
  let vaultName = $derived(props.vaultName);
  let open = $derived(props.open ?? false);
  let openCommandPalette = $derived(props.openCommandPalette ?? (() => {}));
  let closeDrawer = $derived(props.closeDrawer ?? (() => {}));

  let activePath = $derived(decodeURIComponent($page.url.pathname));

  let navItems = $derived<NavItem[]>([
    {
      id: 'notes',
      label: 'Notes',
      meta: 'index',
      href: `/${vaultName}`
    },
    {
      id: 'search',
      label: 'Search',
      meta: 'cmdk',
      action: openCommandPalette
    },
    {
      id: 'tags',
      label: 'Tags',
      meta: 'pending',
      disabled: true
    },
    {
      id: 'graph',
      label: 'Graph',
      meta: 'network',
      href: `/${vaultName}/graph`
    },
    {
      id: 'ask',
      label: 'Ask',
      meta: 'agent',
      href: `/${vaultName}/ask`
    },
    {
      id: 'logger',
      label: 'Logger',
      meta: 'daily log',
      href: `/${vaultName}/logger`
    },
    {
      id: 'workflows',
      label: 'Workflows',
      meta: 'automation',
      href: `/${vaultName}/workflows`
    },
    {
      id: 'daily',
      label: 'Daily',
      meta: 'ledger',
      href: `/${vaultName}/daily`
    }
  ]);

  function isActive(item: NavItem) {
    if (!item.href) return false;
    if (item.id === 'notes') return activePath === item.href;
    return activePath === item.href || activePath.startsWith(`${item.href}/`);
  }

  function runItem(item: NavItem) {
    if (item.disabled) return;
    if (item.action) {
      closeDrawer();
      item.action();
      return;
    }
    if (item.href) {
      closeDrawer();
      void goto(item.href);
    }
  }

  function onItemKeydown(event: KeyboardEvent, item: NavItem) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    event.stopPropagation();
    runItem(item);
  }
</script>

<aside class="app-nav-drawer" class:open aria-hidden={!open} aria-label="App navigation">
  <div class="drawer-inner">
    <div class="drawer-header">
      <span class="drawer-title">navigation</span>
      <span class="drawer-count">8 channels</span>
    </div>

    <nav class="nav-list" aria-label="Vault sections">
      {#each navItems as item (item.id)}
        {#if item.disabled}
          <div
            role="button"
            class="nav-item"
            class:active={isActive(item)}
            class:disabled={item.disabled}
            aria-label={item.label}
            aria-current={isActive(item) ? 'page' : undefined}
            aria-disabled="true"
            tabindex={open ? 0 : -1}
            onclick={(event) => {
              event.preventDefault();
              event.stopPropagation();
            }}
            onkeydown={(event) => onItemKeydown(event, item)}
          >
            <span class="nav-label">{item.label}</span>
            <span class="nav-meta" aria-hidden="true">{item.meta}</span>
          </div>
        {:else}
          <button
            type="button"
            class="nav-item"
            class:active={isActive(item)}
            aria-label={item.label}
            aria-current={isActive(item) ? 'page' : undefined}
            tabindex={open ? 0 : -1}
            onclick={() => runItem(item)}
            onkeydown={(event) => onItemKeydown(event, item)}
          >
            <span class="nav-label">{item.label}</span>
            <span class="nav-meta" aria-hidden="true">{item.meta}</span>
          </button>
        {/if}
      {/each}
    </nav>
  </div>
</aside>

<style>
  .app-nav-drawer {
    --nav-rail: var(--rail);
    position: relative;
    z-index: 90;
    flex-shrink: 0;
    width: 0;
    overflow: hidden;
    background: var(--surface);
    border-right: 1px solid var(--border);
    transition: width var(--dur-base, 200ms) var(--ease-out);
  }

  .app-nav-drawer.open {
    width: var(--phase2-drawer-width, 300px);
  }

  .app-nav-drawer::after {
    content: '';
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    width: 1px;
    background: var(--nav-rail);
    opacity: 0;
    transition: opacity var(--dur-base, 200ms) var(--ease-out);
  }

  .app-nav-drawer.open::after {
    opacity: 1;
  }

  .drawer-inner {
    width: var(--phase2-drawer-width, 300px);
    height: 100%;
    overflow-y: auto;
    transform: translateX(calc(-1 * var(--phase2-drawer-width, 300px)));
    transition: transform var(--dur-base, 200ms) var(--ease-out);
  }

  .app-nav-drawer.open .drawer-inner {
    transform: translateX(0);
  }

  .drawer-header {
    position: sticky;
    top: 0;
    z-index: 1;
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: var(--space-3, 12px);
    padding: var(--space-4, 16px);
    background: var(--surface);
    border-top: 2px solid var(--signal);
    border-bottom: 1px solid var(--border);
  }

  .drawer-title,
  .drawer-count,
  .nav-item {
    font-family: var(--font-mono);
  }

  .drawer-title {
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: var(--type-chrome-sm-weight, 600);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--text);
  }

  .drawer-count {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-faint);
    white-space: nowrap;
  }

  .nav-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-1, 4px);
    padding: var(--space-3, 12px) 0 var(--space-5, 24px);
  }

  .nav-item {
    position: relative;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    min-height: 42px;
    width: 100%;
    padding: 0 var(--space-4, 16px);
    text-align: left;
    color: var(--text-muted);
    background: transparent;
    border: 0;
    border-top: 1px solid transparent;
    border-bottom: 1px solid transparent;
    cursor: pointer;
    appearance: none;
    transition:
      color var(--dur-fast, 120ms) var(--ease-out),
      background-color var(--dur-fast, 120ms) var(--ease-out),
      border-color var(--dur-fast, 120ms) var(--ease-out);
  }

  .nav-item::before {
    content: '';
    position: absolute;
    left: 0;
    top: 8px;
    bottom: 8px;
    width: 2px;
    background: var(--signal);
    opacity: 0;
    transition: opacity var(--dur-fast, 120ms) var(--ease-out);
  }

  .nav-label,
  .nav-meta {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .nav-label {
    font-size: var(--type-chrome-size, 13px);
    color: inherit;
  }

  .nav-meta {
    font-size: var(--type-chrome-sm-size, 11px);
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.10em;
  }

  .nav-item:hover,
  .nav-item:focus-visible,
  .nav-item.active {
    color: var(--text);
    background-color: var(--accent-bg);
    border-color: var(--border);
    outline: none;
  }

  .nav-item:hover::before,
  .nav-item:focus-visible::before,
  .nav-item.active::before {
    opacity: 1;
  }

  .nav-item.disabled {
    cursor: default;
    color: var(--text-faint);
  }

  .nav-item.disabled:hover,
  .nav-item.disabled:focus-visible {
    background: transparent;
    border-color: transparent;
  }

  .nav-item.disabled:hover::before,
  .nav-item.disabled:focus-visible::before {
    opacity: 0;
  }

  @media (max-width: 760px) {
    .app-nav-drawer {
      position: absolute;
      top: 0;
      left: 8px;
      bottom: 0;
      width: min(var(--phase2-drawer-width, 300px), calc(100vw - 32px));
      max-width: calc(100vw - 32px);
      transform: translateX(calc(-100% - 8px));
      transition: transform var(--dur-base, 200ms) var(--ease-out);
    }

    .app-nav-drawer.open {
      width: min(var(--phase2-drawer-width, 300px), calc(100vw - 32px));
      transform: translateX(0);
    }

    .drawer-inner {
      width: min(var(--phase2-drawer-width, 300px), calc(100vw - 32px));
      transform: none;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .app-nav-drawer,
    .app-nav-drawer::after,
    .drawer-inner,
    .nav-item,
    .nav-item::before {
      transition: none;
    }
  }
</style>
