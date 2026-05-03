<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { apiGet } from '$lib/api/client.js';

  interface NoteItem {
    note_id: string;
    title: string;
    tags: string[];
  }

  interface FolderGroup {
    prefix: string;
    items: NoteItem[];
  }

  interface Props {
    vaultName: string;
    open?: boolean;
  }

  let { vaultName, open = false }: Props = $props();

  let notes = $state<NoteItem[]>([]);
  let loading = $state(true);
  let error = $state('');
  let activePath = $derived(decodeURIComponent($page.url.pathname));

  function buildGroups(items: NoteItem[]): FolderGroup[] {
    const map = new Map<string, NoteItem[]>();
    for (const note of items) {
      const slash = note.note_id.indexOf('/');
      const prefix = slash !== -1 ? note.note_id.slice(0, slash) : '(root)';
      if (!map.has(prefix)) map.set(prefix, []);
      map.get(prefix)!.push(note);
    }
    return Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([prefix, entries]) => ({
        prefix,
        items: entries.toSorted((a, b) => (a.title || a.note_id).localeCompare(b.title || b.note_id))
      }));
  }

  let groups = $derived<FolderGroup[]>(buildGroups(notes));
  let noteCount = $derived(notes.length);

  onMount(async () => {
    try {
      const data = await apiGet<NoteItem[]>(`/api/v1/vault/${vaultName}/notes`);
      notes = Array.isArray(data) ? data : [];
    } catch {
      error = 'Failed to load notes.';
    } finally {
      loading = false;
    }
  });
</script>

<aside class="file-tree-drawer" class:open aria-hidden={!open} aria-label="File drawer">
  <div class="drawer-inner">
    <div class="drawer-header">
      <span class="drawer-title">file bay</span>
      <span class="drawer-count">{noteCount} notes</span>
    </div>
    <div class="drawer-body">
      {#if loading}
        <p class="status">Loading note index…</p>
      {:else if error}
        <p class="status error">{error}</p>
      {:else if groups.length === 0}
        <p class="status">No notes.</p>
      {:else}
        <nav class="tree" aria-label="Notes by folder">
          {#each groups as group (group.prefix)}
            <section class="folder">
              <p class="folder-label"><span>{group.prefix}</span><span>{group.items.length}</span></p>
              <ul class="note-list">
                {#each group.items as note (note.note_id)}
                  <li>
                    <button
                      class="note-item"
                      class:active={activePath === `/${vaultName}/notes/${note.note_id}`}
                      tabindex={open ? 0 : -1}
                      onclick={() => goto(`/${vaultName}/notes/${note.note_id}`)}
                    >
                      <span class="note-title">{note.title || note.note_id}</span>
                      <span class="note-id">{note.note_id}</span>
                    </button>
                  </li>
                {/each}
              </ul>
            </section>
          {/each}
        </nav>
      {/if}
    </div>
  </div>
</aside>

<style>
  .file-tree-drawer {
    --bg: #090b0d;
    --bg-elev: #101419;
    --surface: #101419;
    --text: #e8ecef;
    --text-muted: #9aa6ad;
    --text-faint: #5f6970;
    --border: rgba(159, 177, 188, 0.20);
    --accent: #ecaa4a;
    --accent-bg: rgba(236, 170, 74, 0.12);
    --signal: #ecaa4a;
    --signal-danger: #ff6b5f;
    --rail: rgba(236, 170, 74, 0.58);
    position: relative;
    z-index: 90;
    flex-shrink: 0;
    width: 0;
    overflow: hidden;
    background:
      linear-gradient(180deg, rgba(236, 170, 74, 0.08), transparent 140px),
      var(--surface, var(--bg-elev, #101419));
    border-right: 1px solid var(--border, rgba(159, 177, 188, 0.20));
    transition: width var(--dur-base, 200ms) var(--ease-out);
  }

  .file-tree-drawer.open {
    width: var(--phase2-drawer-width, 300px);
  }

  .file-tree-drawer::after {
    content: '';
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    width: 1px;
    background: linear-gradient(180deg, var(--rail, rgba(236, 170, 74, 0.58)), transparent 44%);
    opacity: 0;
    transition: opacity var(--dur-base, 200ms) var(--ease-out);
  }

  .file-tree-drawer.open::after {
    opacity: 1;
  }

  .drawer-inner {
    width: var(--phase2-drawer-width, 300px);
    height: 100%;
    overflow-y: auto;
    transform: translateX(calc(-1 * var(--phase2-drawer-width, 300px)));
    transition: transform var(--dur-base, 200ms) var(--ease-out);
  }

  .file-tree-drawer.open .drawer-inner {
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
    background: var(--surface, var(--bg-elev, #101419));
    border-top: 2px solid var(--signal, var(--accent, #ecaa4a));
    border-bottom: 1px solid var(--border, rgba(159, 177, 188, 0.20));
  }

  .drawer-title,
  .drawer-count,
  .folder-label,
  .status,
  .note-item {
    font-family: var(--font-mono);
  }

  .drawer-title {
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: var(--type-chrome-sm-weight, 500);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--text, #e8ecef);
  }

  .drawer-count {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-faint, #5f6970);
    white-space: nowrap;
  }

  .drawer-body {
    padding: var(--space-3, 12px) 0 var(--space-5, 24px);
  }

  .status {
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-muted, #9aa6ad);
    padding: 0 var(--space-4, 16px);
    margin: 0;
  }

  .status.error {
    color: var(--signal-danger, #ff6b5f);
  }

  .tree {
    display: flex;
    flex-direction: column;
    gap: var(--space-4, 16px);
  }

  .folder {
    display: flex;
    flex-direction: column;
    gap: var(--space-1, 4px);
    border-left: 1px solid rgba(236, 170, 74, 0.20);
    margin-left: var(--space-4, 16px);
  }

  .folder-label {
    display: flex;
    justify-content: space-between;
    gap: var(--space-3, 12px);
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: var(--type-chrome-sm-weight, 500);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-faint, #5f6970);
    padding: 0 var(--space-4, 16px) 0 var(--space-3, 12px);
    margin: 0 0 var(--space-1, 4px);
  }

  .note-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
  }

  .note-item {
    position: relative;
    display: grid;
    width: 100%;
    min-height: 38px;
    text-align: left;
    background: transparent;
    border: 0;
    border-top: 1px solid transparent;
    border-bottom: 1px solid transparent;
    cursor: pointer;
    font-size: var(--type-chrome-size, 13px);
    line-height: 1.35;
    color: var(--text, #e8ecef);
    padding: var(--space-2, 8px) var(--space-4, 8px) var(--space-2, 8px) var(--space-3, 12px);
    overflow: hidden;
    transition:
      color var(--dur-fast, 120ms) var(--ease-out),
      background-color var(--dur-fast, 120ms) var(--ease-out),
      border-color var(--dur-fast, 120ms) var(--ease-out);
  }

  .note-item::before {
    content: '';
    position: absolute;
    left: 0;
    top: 8px;
    bottom: 8px;
    width: 2px;
    background: var(--signal, var(--accent, #ecaa4a));
    opacity: 0;
    transition: opacity var(--dur-fast, 120ms) var(--ease-out);
  }

  .note-title,
  .note-id {
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .note-id {
    color: var(--text-faint, #5f6970);
    font-size: 11px;
  }

  .note-item:hover,
  .note-item:focus-visible,
  .note-item.active {
    color: var(--text, #e8ecef);
    background-color: var(--accent-bg, rgba(236, 170, 74, 0.12));
    border-color: var(--border, rgba(159, 177, 188, 0.20));
    outline: none;
  }

  .note-item:hover::before,
  .note-item:focus-visible::before,
  .note-item.active::before {
    opacity: 1;
  }

  @media (max-width: 760px) {
    .file-tree-drawer {
      position: absolute;
      top: 0;
      left: 8px;
      bottom: 0;
      width: min(var(--phase2-drawer-width, 300px), calc(100vw - 32px));
      max-width: calc(100vw - 32px);
      transform: translateX(calc(-100% - 8px));
      transition: transform var(--dur-base, 200ms) var(--ease-out);
    }

    .file-tree-drawer.open {
      width: min(var(--phase2-drawer-width, 300px), calc(100vw - 32px));
      transform: translateX(0);
    }

    .drawer-inner {
      width: min(var(--phase2-drawer-width, 300px), calc(100vw - 32px));
      transform: none;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .file-tree-drawer,
    .file-tree-drawer::after,
    .drawer-inner,
    .note-item,
    .note-item::before {
      transition: none;
    }
  }
</style>
