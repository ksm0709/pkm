<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { apiGet } from '$lib/api/client.js';

  interface Props {
    vaultName: string;
  }

  let { vaultName }: Props = $props();

  type Theme = 'light' | 'dark' | 'auto';

  type CommandRow = {
    kind: 'command';
    id: string;
    label: string;
    hint?: string;
    run: () => void | Promise<void>;
  };

  type NoteRow = {
    kind: 'note';
    id: string;
    label: string;
    hint?: string;
    note_id: string;
  };

  type Row = CommandRow | NoteRow;

  interface SearchResult {
    note_id: string;
    title: string;
    snippet?: string;
    score?: number;
  }

  interface SearchResponse {
    results: SearchResult[];
    query: string;
    count: number;
  }

  interface TagSearchNote {
    note_id: string;
    title: string;
    tags: string[];
    path: string;
  }

  interface TagSearchResponse {
    pattern: string;
    mode: string;
    results: TagSearchNote[];
    count: number;
  }

  let open = $state(false);
  let query = $state('');
  let activeIndex = $state(0);
  let inputEl: HTMLInputElement | null = $state(null);

  let notes = $state<SearchResult[]>([]);
  let tagNotes = $state<TagSearchNote[]>([]);
  let vaultsList = $state<string[]>([]);

  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let lastQuery = '';

  function dispatchTheme(theme: Theme) {
    window.dispatchEvent(
      new CustomEvent('pkm:theme-change', { detail: { theme } })
    );
  }

  function readStoredTheme(): Theme {
    try {
      const stored = localStorage.getItem('pkm.theme');
      if (stored === 'light' || stored === 'dark' || stored === 'auto') {
        return stored;
      }
    } catch {
      // ignore
    }
    return 'auto';
  }

  function nextTheme(curr: Theme): Theme {
    if (curr === 'light') return 'dark';
    if (curr === 'dark') return 'auto';
    return 'light';
  }

  async function loadVaults() {
    if (vaultsList.length > 0) return;
    try {
      const v = await apiGet<string[]>('/api/v1/vaults');
      vaultsList = Array.isArray(v) ? v : [];
    } catch {
      vaultsList = [];
    }
  }

  function staticCommands(): CommandRow[] {
    const list: CommandRow[] = [
      {
        kind: 'command',
        id: 'cmd:jump',
        label: 'Jump to note…',
        hint: 'type to search',
        run: () => {
          // Focus stays in input; user can keep typing
          inputEl?.focus();
        }
      },
      {
        kind: 'command',
        id: 'cmd:daily',
        label: "Open today's daily note",
        hint: 'daily',
        run: () => goto(`/${vaultName}/daily`)
      },
      {
        kind: 'command',
        id: 'cmd:ask',
        label: 'Ask…',
        hint: 'ask',
        run: () => {
          const q = query.trim();
          const target = q
            ? `/${vaultName}/ask?q=${encodeURIComponent(q)}`
            : `/${vaultName}/ask`;
          return goto(target);
        }
      },
      {
        kind: 'command',
        id: 'cmd:switch',
        label: 'Switch vault…',
        hint: 'switch',
        run: async () => {
          await loadVaults();
          const others = vaultsList.filter((v) => v !== vaultName);
          if (others.length === 0) return;
          // First non-current vault — for full picker behavior the user can
          // start typing the vault name once vaults are listed below.
          await goto(`/${others[0]}`);
          close();
        }
      },
      {
        kind: 'command',
        id: 'cmd:theme',
        label: 'Toggle theme',
        hint: 'theme',
        run: () => {
          const t = nextTheme(readStoredTheme());
          dispatchTheme(t);
        }
      },
      {
        kind: 'command',
        id: 'cmd:graph',
        label: 'Open graph',
        hint: 'graph',
        run: () => goto(`/${vaultName}/graph`)
      }
    ];
    return list;
  }

  function vaultSwitchRows(): CommandRow[] {
    return vaultsList
      .filter((v) => v !== vaultName)
      .map((v) => ({
        kind: 'command' as const,
        id: `vault:${v}`,
        label: `Switch to ${v}`,
        hint: 'vault',
        run: () => goto(`/${v}`)
      }));
  }

  function commandsForQuery(q: string): CommandRow[] {
    const all = staticCommands();
    if (!q) return all;
    const lower = q.toLowerCase();
    return all.filter(
      (c) =>
        c.label.toLowerCase().includes(lower) ||
        (c.hint?.toLowerCase().includes(lower) ?? false)
    );
  }

  let rows = $derived<Row[]>(buildRows(query, notes, tagNotes));

  function buildRows(
    q: string,
    notesList: SearchResult[],
    tagNotesList: TagSearchNote[]
  ): Row[] {
    const trimmed = q.trim();
    if (!trimmed) {
      return staticCommands();
    }

    if (trimmed.startsWith('#')) {
      return tagNotesList.map((n) => ({
        kind: 'note' as const,
        id: `tagnote:${n.note_id}`,
        label: n.title || n.note_id,
        hint: n.tags?.length ? n.tags.map((t) => `#${t}`).join(' ') : undefined,
        note_id: n.note_id
      }));
    }

    const noteRows: NoteRow[] = notesList.map((n) => ({
      kind: 'note',
      id: `note:${n.note_id}`,
      label: n.title || n.note_id,
      hint: n.snippet,
      note_id: n.note_id
    }));

    const cmdRows: CommandRow[] = commandsForQuery(trimmed);
    return [...noteRows, ...cmdRows];
  }

  async function runSearch(q: string) {
    const trimmed = q.trim();
    if (trimmed.length < 2) {
      notes = [];
      tagNotes = [];
      return;
    }

    if (trimmed.startsWith('#')) {
      const pattern = trimmed.slice(1);
      if (!pattern) {
        notes = [];
        tagNotes = [];
        return;
      }
      try {
        const data = await apiGet<TagSearchResponse>(
          `/api/v1/vault/${vaultName}/tags/search?pattern=${encodeURIComponent(pattern)}`
        );
        tagNotes = data.results ?? [];
      } catch {
        tagNotes = [];
      }
      notes = [];
      return;
    }

    try {
      const data = await apiGet<SearchResponse>(
        `/api/v1/vault/${vaultName}/search?q=${encodeURIComponent(trimmed)}`
      );
      notes = data.results ?? [];
    } catch {
      notes = [];
    }
    tagNotes = [];
  }

  function scheduleSearch(q: string) {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      if (q === lastQuery) return;
      lastQuery = q;
      void runSearch(q);
    }, 100);
  }

  function onInput(e: Event) {
    const target = e.target as HTMLInputElement;
    query = target.value;
    activeIndex = 0;
    scheduleSearch(query);
  }

  function openPalette() {
    open = true;
    query = '';
    activeIndex = 0;
    notes = [];
    tagNotes = [];
    lastQuery = '';
    // Pre-fetch vault list so vault switch is instant
    void loadVaults();
    requestAnimationFrame(() => inputEl?.focus());
  }

  function close() {
    open = false;
    if (debounceTimer) {
      clearTimeout(debounceTimer);
      debounceTimer = null;
    }
  }

  async function execute(row: Row) {
    if (row.kind === 'command') {
      await row.run();
      // Most commands navigate; some (theme) keep palette open. Close by default
      // unless the command was the no-op "jump" one.
      if (row.id !== 'cmd:jump') close();
      return;
    }
    if (row.kind === 'note') {
      await goto(`/${vaultName}/notes/${row.note_id}`);
      close();
    }
  }

  function onKeydown(event: KeyboardEvent) {
    // Global ⌘K toggle
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      if (open) close();
      else openPalette();
      return;
    }

    if (!open) return;

    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (rows.length === 0) return;
      activeIndex = (activeIndex + 1) % rows.length;
      return;
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (rows.length === 0) return;
      activeIndex = (activeIndex - 1 + rows.length) % rows.length;
      return;
    }

    if (event.key === 'Enter') {
      event.preventDefault();
      const row = rows[activeIndex];
      if (row) void execute(row);
    }
  }

  function onBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) close();
  }

  onMount(() => {
    // No-op; ⌘K binding lives on svelte:window for global capture.
  });
</script>

<svelte:window onkeydown={onKeydown} />

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="cmdk-backdrop" onclick={onBackdropClick}>
    <div
      class="cmdk-modal"
      role="dialog"
      aria-label="Command palette"
      aria-modal="true"
    >
      <input
        bind:this={inputEl}
        class="cmdk-input"
        type="text"
        placeholder="Search notes, run commands, #tag…"
        value={query}
        oninput={onInput}
        autocomplete="off"
        spellcheck="false"
      />
      <ul class="cmdk-list" role="listbox">
        {#each rows as row, i (row.id)}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <li
            class="cmdk-row"
            class:active={i === activeIndex}
            role="option"
            aria-selected={i === activeIndex}
            onmousemove={() => (activeIndex = i)}
            onclick={() => execute(row)}
          >
            <span class="row-glyph" aria-hidden="true">
              {i === activeIndex ? '→' : ''}
            </span>
            <span class="row-label">{row.label}</span>
            {#if row.hint}
              <span class="row-hint">{row.hint}</span>
            {/if}
          </li>
        {/each}
        {#if rows.length === 0}
          <li class="cmdk-empty">No matches.</li>
        {/if}
      </ul>
    </div>
  </div>
{/if}

<style>
  .cmdk-backdrop {
    position: fixed;
    inset: 0;
    background-color: rgba(20, 17, 13, 0.40);
    z-index: 1000;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding-top: 12vh;
  }

  .cmdk-modal {
    width: var(--palette-width, 560px);
    max-height: var(--palette-max-height, 60vh);
    background-color: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm, 2px);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    /* No shadow */
  }

  .cmdk-input {
    width: 100%;
    box-sizing: border-box;
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    color: var(--text);
    background-color: var(--bg);
    border: none;
    border-bottom: 1px solid var(--border);
    border-radius: 0;
    padding: var(--space-3, 12px) var(--space-4, 16px);
    outline: none;
    caret-color: var(--accent);
  }

  .cmdk-input::placeholder {
    color: var(--text-faint);
  }

  .cmdk-list {
    list-style: none;
    margin: 0;
    padding: var(--space-1, 4px) 0;
    overflow-y: auto;
    flex: 1;
  }

  .cmdk-row {
    display: flex;
    align-items: center;
    gap: var(--space-2, 8px);
    height: 32px;
    padding: 0 var(--space-4, 16px);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    line-height: var(--type-chrome-lh, 1.20);
    color: var(--text);
    cursor: pointer;
  }

  .cmdk-row.active {
    background-color: var(--accent-bg);
  }

  .row-glyph {
    width: 12px;
    color: var(--accent);
    flex-shrink: 0;
  }

  .row-label {
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .row-hint {
    color: var(--text-faint);
    font-size: var(--type-chrome-sm-size, 11px);
    flex-shrink: 0;
    margin-left: var(--space-3, 12px);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 240px;
  }

  .cmdk-empty {
    padding: var(--space-3, 12px) var(--space-4, 16px);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-faint);
  }
</style>
