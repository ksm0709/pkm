<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { page } from '$app/stores';
  import { apiGet } from '$lib/api/client.js';

  interface DailyEntry {
    note_id?: string;
    date: string; // YYYY-MM-DD
    kind?: 'daily' | 'subnote';
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

  function noteIdFor(entry: DailyEntry) {
    return entry.note_id || entry.date;
  }

  function isSubnote(entry: DailyEntry) {
    return entry.kind === 'subnote' || noteIdFor(entry) !== entry.date;
  }

  function subnoteLabel(entry: DailyEntry) {
    const noteId = noteIdFor(entry);
    const fallback = noteId.startsWith(`${entry.date}-`)
      ? noteId.slice(entry.date.length + 1)
      : noteId;
    return entry.title && entry.title !== noteId ? entry.title : fallback;
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
    <ul class="entry-list" aria-label="Daily notes">
      {#each entries as entry (noteIdFor(entry))}
        <li
          class="entry"
          class:is-today={entry.date === today && !isSubnote(entry)}
          class:is-subnote={isSubnote(entry)}
        >
          <a class="entry-link" href="/{vaultName}/notes/{noteIdFor(entry)}">
            {#if isSubnote(entry)}
              <span class="entry-title">{subnoteLabel(entry)}</span>
              <span class="entry-meta" aria-hidden="true">{entry.date}</span>
            {:else}
              {entry.date}
            {/if}
          </a>
        </li>
      {/each}
    </ul>
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

  .entry.is-subnote {
    min-height: 38px;
  }

  .entry-link {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3, 12px);
    min-height: 40px;
    padding-left: var(--space-3, 12px);
    padding-right: var(--space-3, 12px);
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    text-decoration: none;
    color: var(--text);
    transition: background-color var(--dur-fast, 120ms) var(--ease-out), color var(--dur-fast, 120ms) var(--ease-out);
  }

  .entry.is-subnote .entry-link {
    min-height: 38px;
    padding-left: var(--space-6, 32px);
    color: var(--text-muted);
    font-size: var(--type-chrome-size, 13px);
  }

  .entry-title {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .entry-meta {
    flex-shrink: 0;
    color: var(--text-faint);
    font-size: var(--type-chrome-sm-size, 11px);
  }

  .entry-link:hover,
  .entry-link:focus-visible {
    background: var(--accent-bg);
    outline: none;
  }

  .entry-link:hover,
  .entry-link:focus-visible {
    color: var(--accent);
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
      padding-block: var(--space-2, 8px);
    }
  }
</style>
