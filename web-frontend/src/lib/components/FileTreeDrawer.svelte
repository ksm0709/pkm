<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
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
      .map(([prefix, entries]) => ({ prefix, items: entries }));
  }

  let groups = $derived<FolderGroup[]>(buildGroups(notes));

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

<aside class="file-tree-drawer" class:open aria-hidden={!open}>
  <div class="drawer-inner">
    <div class="drawer-header">
      <span class="drawer-title">FILES</span>
    </div>
    <div class="drawer-body">
      {#if loading}
        <p class="status">Loading…</p>
      {:else if error}
        <p class="status error">{error}</p>
      {:else if groups.length === 0}
        <p class="status">No notes.</p>
      {:else}
        <nav class="tree">
          {#each groups as group (group.prefix)}
            <section class="folder">
              <p class="folder-label">{group.prefix}</p>
              <ul class="note-list">
                {#each group.items as note (note.note_id)}
                  <li>
                    <button
                      class="note-item"
                      tabindex={open ? 0 : -1}
                      onclick={() => goto(`/${vaultName}/notes/${note.note_id}`)}
                    >
                      {note.title || note.note_id}
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
  /* Outer shell: starts at 0-width, expands to --drawer-width when open.
     Overflow hidden hides the translated inner content while collapsed.
     This is what *pushes* sibling content right. */
  .file-tree-drawer {
    flex-shrink: 0;
    width: 0;
    overflow: hidden;
    background-color: var(--bg-elev);
    border-right: 1px solid var(--border);
    transition: width var(--dur-base, 200ms) var(--ease-out);
    /* No box-shadow */
  }

  .file-tree-drawer.open {
    width: var(--drawer-width, 280px);
  }

  /* Inner shell: fixed width, slides in via transform: translateX.
     Both transitions run in sync so the slide effect matches the push. */
  .drawer-inner {
    width: var(--drawer-width, 280px);
    height: 100%;
    overflow-y: auto;
    transform: translateX(calc(-1 * var(--drawer-width, 280px)));
    transition: transform var(--dur-base, 200ms) var(--ease-out);
  }

  .file-tree-drawer.open .drawer-inner {
    transform: translateX(0);
  }

  .drawer-header {
    padding: var(--space-4, 16px) var(--space-4, 16px) var(--space-3, 12px);
    border-bottom: 1px solid var(--border);
  }

  .drawer-title {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: var(--type-chrome-sm-weight, 500);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-faint);
  }

  .drawer-body {
    padding: var(--space-3, 12px) 0;
  }

  .status {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-muted);
    padding: 0 var(--space-4, 16px);
    margin: 0;
  }

  .status.error {
    color: #c0392b;
  }

  .tree {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 12px);
  }

  .folder {
    display: flex;
    flex-direction: column;
    gap: var(--space-1, 4px);
  }

  .folder-label {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: var(--type-chrome-sm-weight, 500);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-faint);
    padding: 0 var(--space-4, 16px);
    margin: 0 0 var(--space-1, 4px);
  }

  .note-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 12px);
  }

  .note-item {
    display: block;
    width: 100%;
    text-align: left;
    background: none;
    border: none;
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    line-height: var(--type-body-lh, 1.70);
    color: var(--text);
    padding: 0 var(--space-4, 16px);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .note-item:hover {
    color: var(--accent);
    background-color: var(--accent-bg);
  }
</style>
