<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { page } from '$app/stores';
  import { apiGet } from '$lib/api/client.js';

  interface DailyEntry {
    date: string; // YYYY-MM-DD
    title: string;
    todo_count: number;
    snippet: string;
  }

  let vaultName = $derived($page.params.vault);

  let entries = $state<DailyEntry[]>([]);
  let loading = $state(false);
  let initialLoading = $state(true);
  let error = $state('');
  let hasMore = $state(true);

  const today = new Date().toISOString().slice(0, 10);
  const PAGE_SIZE = 50;

  let sentinel: HTMLDivElement | null = $state(null);
  let observer: IntersectionObserver | null = null;

  const monthFormatter = new Intl.DateTimeFormat('en-US', {
    month: 'long',
    year: 'numeric'
  });
  const dayFormatter = new Intl.DateTimeFormat('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric'
  });

  function monthKey(date: string): string {
    return date.slice(0, 7); // YYYY-MM
  }

  function monthLabel(date: string): string {
    // Parse as local-date-only (avoid TZ shift): construct via parts.
    const [y, m] = date.split('-').map(Number);
    const d = new Date(y, m - 1, 1);
    return monthFormatter.format(d).toUpperCase();
  }

  function formatDay(date: string): string {
    const [y, m, d] = date.split('-').map(Number);
    return dayFormatter.format(new Date(y, m - 1, d));
  }

  // Group entries by month, preserving the descending order they arrive in.
  const grouped = $derived.by(() => {
    const groups: { key: string; label: string; items: DailyEntry[] }[] = [];
    let current: { key: string; label: string; items: DailyEntry[] } | null = null;
    for (const entry of entries) {
      const key = monthKey(entry.date);
      if (!current || current.key !== key) {
        current = { key, label: monthLabel(entry.date), items: [] };
        groups.push(current);
      }
      current.items.push(entry);
    }
    return groups;
  });

  async function loadPage(beforeCursor: string) {
    if (loading || !hasMore) return;
    loading = true;
    try {
      const url = `/api/v1/vault/${vaultName}/daily?before=${encodeURIComponent(beforeCursor)}&limit=${PAGE_SIZE}`;
      const batch = await apiGet<DailyEntry[]>(url);
      if (!Array.isArray(batch) || batch.length === 0) {
        hasMore = false;
      } else {
        entries = [...entries, ...batch];
        if (batch.length < PAGE_SIZE) hasMore = false;
      }
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load daily notes.';
      hasMore = false;
    } finally {
      loading = false;
      initialLoading = false;
    }
  }

  function loadMore() {
    if (loading || !hasMore) return;
    if (entries.length === 0) {
      // Use today + 1 day as exclusive upper bound so today is included.
      const [y, m, d] = today.split('-').map(Number);
      const next = new Date(y, m - 1, d + 1);
      const cursor = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}-${String(next.getDate()).padStart(2, '0')}`;
      loadPage(cursor);
    } else {
      const oldest = entries[entries.length - 1].date;
      loadPage(oldest);
    }
  }

  $effect(() => {
    if (sentinel && hasMore && !observer) {
      observer = new IntersectionObserver(
        (entries) => {
          for (const e of entries) {
            if (e.isIntersecting) loadMore();
          }
        },
        { rootMargin: '200px' }
      );
      observer.observe(sentinel);
    }
  });

  onMount(() => {
    loadMore();
  });

  onDestroy(() => {
    observer?.disconnect();
    observer = null;
  });

  // Vim-ish two-char sequences on the timeline (no editor focused here):
  //   gd → today's daily, gn/gp → next/prev neighbor, gx → external,
  //   <leader>k (Space + k) → ⌘K palette. Mirrors the editor mappings
  //   from F4-5 so the timeline page is reachable from itself.
  let pending = '';
  let pendingTimer: ReturnType<typeof setTimeout> | null = null;

  function isTypingTarget(t: EventTarget | null): boolean {
    if (!(t instanceof HTMLElement)) return false;
    const tag = t.tagName;
    return (
      tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || t.isContentEditable
    );
  }

  function handleKeydown(e: KeyboardEvent): void {
    if (isTypingTarget(e.target)) return;
    const nav = (window as any).__pkmNav as Record<string, () => void> | undefined;
    if (!nav) return;
    const key = e.key;
    if (pending === 'g') {
      pending = '';
      if (pendingTimer) clearTimeout(pendingTimer);
      pendingTimer = null;
      const map: Record<string, string> = {
        d: 'gotoDaily', n: 'nextNeighbor', p: 'prevNeighbor', x: 'openExternal'
      };
      const action = map[key];
      if (action && typeof nav[action] === 'function') {
        e.preventDefault();
        nav[action]();
      }
      return;
    }
    if (pending === ' ' && key === 'k') {
      pending = '';
      if (pendingTimer) clearTimeout(pendingTimer);
      pendingTimer = null;
      if (typeof nav.openPalette === 'function') {
        e.preventDefault();
        nav.openPalette();
      }
      return;
    }
    if (key === 'g' || key === ' ') {
      pending = key;
      if (pendingTimer) clearTimeout(pendingTimer);
      pendingTimer = setTimeout(() => { pending = ''; pendingTimer = null; }, 800);
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<svelte:head>
  <title>Daily — {vaultName}</title>
</svelte:head>

<main class="reading-column daily-timeline">
  <header class="timeline-header">
    <p>EVENT LEDGER</p>
    <h1>Daily</h1>
  </header>

  {#if error}
    <p class="status-msg error">{error}</p>
  {/if}

  {#if initialLoading}
    <div class="skeleton-list" aria-hidden="true">
      {#each Array(6) as _, i (i)}
        <div class="skeleton-row"></div>
      {/each}
    </div>
  {:else if entries.length === 0 && !error}
    <p class="status-msg faint">No daily notes yet.</p>
  {:else}
    {#each grouped as group (group.key)}
      <section class="month-block">
        <div class="month-rule">
          <span class="month-label">{group.label}</span>
          <span class="month-line" aria-hidden="true"></span>
        </div>
        <ul class="entry-list">
          {#each group.items as entry (entry.date)}
            <li class="entry" class:is-today={entry.date === today}>
              <a class="entry-link" href="/{vaultName}/notes/{entry.date}">
                <span class="entry-date">{formatDay(entry.date)}</span>
                <span class="entry-snippet">{entry.snippet || entry.title}</span>
                {#if entry.todo_count > 0}
                  <span class="entry-todos"
                    >{entry.todo_count} todo{entry.todo_count === 1 ? '' : 's'} open</span
                  >
                {/if}
              </a>
            </li>
          {/each}
        </ul>
      </section>
    {/each}
  {/if}

  <div bind:this={sentinel} class="sentinel">
    {#if loading && !initialLoading}
      <span class="status-msg faint">Loading…</span>
    {:else if !hasMore && entries.length > 0}
      <span class="status-msg faint">End of timeline</span>
    {/if}
  </div>
</main>

<style>
  .daily-timeline {
    padding-top: var(--space-6, 32px);
    padding-bottom: var(--space-8, 64px);
    min-height: 60vh;
  }

  .timeline-header {
    border-left: 1px solid var(--accent);
    padding-left: var(--space-4, 16px);
    margin-bottom: var(--space-6, 32px);
  }

  .timeline-header p {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-faint);
    margin: 0;
  }

  h1 {
    font-family: var(--font-display);
    font-size: clamp(34px, 6vw, 44px);
    line-height: 1;
    font-weight: var(--type-h1-weight, 600);
    color: var(--text);
    margin: var(--space-2, 8px) 0 0;
  }

  .month-block {
    margin-bottom: var(--space-6, 32px);
  }

  .month-rule {
    display: flex;
    align-items: center;
    gap: var(--space-3, 12px);
    margin-bottom: var(--space-4, 16px);
  }

  .month-label {
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.18em;
    color: var(--text-faint);
    text-transform: uppercase;
    flex-shrink: 0;
  }

  .month-line {
    flex: 1;
    height: 1px;
    background: var(--border, rgba(0, 0, 0, 0.08));
  }

  .entry-list {
    display: flex;
    flex-direction: column;
    list-style: none;
    margin: 0;
    padding: 0;
    border-top: 1px solid var(--border);
  }

  .entry {
    min-height: 40px;
    border-left: 2px solid transparent;
    border-bottom: 1px solid var(--border);
  }

  .entry.is-today {
    border-left-color: var(--accent, #3a7);
  }

  .entry-link {
    display: grid;
    grid-template-columns: 13ch minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-3, 12px);
    min-height: 40px;
    padding-left: var(--space-3, 12px);
    text-decoration: none;
    color: var(--text);
    transition: background-color var(--dur-fast, 120ms) var(--ease-out), color var(--dur-fast, 120ms) var(--ease-out);
  }

  .entry-link:hover,
  .entry-link:focus-visible {
    background: var(--accent-bg);
    outline: none;
  }

  .entry-link:hover .entry-snippet,
  .entry-link:focus-visible .entry-snippet {
    color: var(--accent);
  }

  .entry-date {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-muted);
  }

  .entry-snippet {
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    color: var(--text);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .entry-todos {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--accent);
    border: 1px solid var(--border);
    padding: 2px 6px;
    flex-shrink: 0;
  }

  .skeleton-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 12px);
  }

  .skeleton-row {
    height: 40px;
    background: var(--accent-bg);
    border-radius: 2px;
    opacity: 0.6;
  }

  .sentinel {
    min-height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-4, 16px) 0;
  }

  .status-msg {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-muted);
  }

  .status-msg.error {
    color: #c0392b;
  }

  .status-msg.faint {
    color: var(--text-faint);
  }

  @media (max-width: 640px) {
    .entry-link {
      grid-template-columns: 1fr;
      gap: 3px;
      padding-block: var(--space-2, 8px);
    }

    .entry-todos {
      justify-self: start;
    }
  }
</style>
