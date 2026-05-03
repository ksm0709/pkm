<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { marked } from 'marked';
  import { apiGet } from '$lib/api/client.js';
  import NeighborPanel from '$lib/components/NeighborPanel.svelte';
  import CodeMirror from '$lib/editor/CodeMirror.svelte';

  interface Note {
    note_id: string;
    title: string;
    body: string;
    frontmatter: Record<string, unknown>;
    created: string | null;
    updated: string | null;
    tags: string[];
    importance: number | null;
  }

  interface NeighborData {
    note_id: string;
    outbound: { note_id: string; title: string; type: string }[];
    inbound: { note_id: string; title: string; type: string }[];
    semantic: { note_id: string; title: string; type: string; confidence?: number }[];
  }

  let note = $state<Note | null>(null);
  let neighbors = $state<NeighborData | null>(null);
  let loadingNote = $state(true);
  let loadingNeighbors = $state(true);
  let error = $state('');
  let renderedBody = $state('');
  let editMode = $state(false);
  let editorDoc = $state('');

  let vaultName = $derived($page.params.vault);
  let noteId = $derived($page.params.id);

  onMount(async () => {
    // Fetch note and neighbors in parallel
    const [noteResult, neighborsResult] = await Promise.allSettled([
      apiGet<Note>(`/api/v1/vault/${vaultName}/notes/${noteId}`),
      apiGet<NeighborData>(`/api/v1/vault/${vaultName}/notes/${noteId}/neighbors`)
    ]);

    if (noteResult.status === 'fulfilled') {
      note = noteResult.value;
      editorDoc = note.body ?? '';
      renderedBody = await marked.parse(note.body ?? '', { async: true });
    } else {
      error = 'Note not found.';
    }
    loadingNote = false;

    if (neighborsResult.status === 'fulfilled') {
      neighbors = neighborsResult.value;
    }
    loadingNeighbors = false;

    // Track last vault
    localStorage.setItem('pkm.lastVault', vaultName);
  });
</script>

<svelte:head>
  <title>{note?.title ?? noteId} — pkm</title>
</svelte:head>

<div class="note-page reading-column">
  {#if loadingNote}
    <p class="status">Loading…</p>
  {:else if error}
    <p class="status error">{error}</p>
  {:else if note}
    <article class="note-article">
      <header class="note-header">
        <div class="meta-rail">
          <span>NOTE</span>
          <span>{note.note_id}</span>
          {#if note.updated}
            <span>updated {note.updated}</span>
          {:else if note.created}
            <span>created {note.created}</span>
          {/if}
          {#if note.importance !== null}
            <span>imp {note.importance}</span>
          {/if}
        </div>
        <div class="title-row">
          <h1>{note.title || note.note_id}</h1>
          <div class="mode-toggle" aria-label="Display mode">
            <button
              type="button"
              class:active={!editMode}
              onclick={() => (editMode = false)}
            >
              Read
            </button>
            <button
              type="button"
              class:active={editMode}
              onclick={() => (editMode = true)}
            >
              Edit
            </button>
          </div>
        </div>
        {#if note.tags?.length}
          <p class="note-tags">
            {#each note.tags as tag}
              <span class="tag">#{tag}</span>
            {/each}
          </p>
        {/if}
      </header>

      {#if editMode}
        <div class="note-editor">
          <CodeMirror bind:doc={editorDoc} />
        </div>
      {:else}
        <!-- Rendered markdown body -->
        <!-- eslint-disable-next-line svelte/no-at-html-tags -->
        <div class="note-body prose">{@html renderedBody}</div>
      {/if}

      <!-- Signature NeighborPanel -->
      <NeighborPanel
        {vaultName}
        data={neighbors}
        loading={loadingNeighbors}
      />
    </article>
  {/if}
</div>

<style>
  .note-page {
    padding-top: var(--space-6, 32px);
    padding-bottom: var(--space-8, 64px);
  }

  .note-article {
    width: 100%;
  }

  .note-header {
    margin-bottom: var(--space-5, 24px);
    border-left: 1px solid var(--accent);
    padding-left: var(--space-4, 16px);
  }

  .meta-rail {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3, 12px);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.12em;
  }

  .title-row {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: var(--space-5, 24px);
    margin-top: var(--space-2, 8px);
  }

  h1 {
    font-family: var(--font-display);
    font-size: clamp(34px, 6vw, 44px);
    line-height: 1;
    font-weight: var(--type-h1-weight, 600);
    color: var(--text);
    margin: 0;
  }

  .note-tags {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2, 8px);
    margin: var(--space-3, 12px) 0 0;
  }

  .tag {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-muted);
  }

  .mode-toggle {
    display: flex;
    align-items: center;
    width: 124px;
    flex-shrink: 0;
    border: 1px solid var(--border);
  }

  .mode-toggle button {
    flex: 1;
    background: none;
    border: none;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    padding: 7px 8px;
    cursor: pointer;
  }

  .mode-toggle button + button {
    border-left: 1px solid var(--border);
  }

  .mode-toggle button.active,
  .mode-toggle button:hover {
    color: var(--bg);
    background: var(--accent);
  }

  .note-editor {
    min-height: 60vh;
    border: 1px solid var(--border);
    margin-bottom: var(--space-5, 24px);
    background: var(--surface-prose, var(--bg-elev));
  }

  .note-body {
    background: var(--surface-prose, var(--bg-elev));
    border: 1px solid var(--border);
    padding: clamp(24px, 5vw, 48px);
    margin-bottom: var(--space-5, 24px);
  }

  /* Prose styles for rendered markdown */
  .prose :global(h1) {
    font-family: var(--font-display);
    font-size: var(--type-h1-size, 28px);
    font-weight: var(--type-h1-weight, 600);
    line-height: var(--type-h1-lh, 1.20);
    color: var(--text);
    margin-bottom: var(--space-4, 16px);
  }

  .prose :global(h2) {
    font-family: var(--font-display);
    font-size: var(--type-h2-size, 20px);
    font-weight: var(--type-h2-weight, 600);
    line-height: var(--type-h2-lh, 1.30);
    color: var(--text);
    margin-top: var(--space-6, 32px);
    margin-bottom: var(--space-3, 12px);
  }

  .prose :global(h3) {
    font-family: var(--font-display);
    font-size: var(--type-h3-size, 17px);
    font-weight: var(--type-h3-weight, 600);
    line-height: var(--type-h3-lh, 1.35);
    color: var(--text);
    margin-top: var(--space-5, 24px);
    margin-bottom: var(--space-2, 8px);
  }

  .prose :global(p) {
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.70);
    color: var(--text);
    margin-bottom: var(--space-4, 16px);
  }

  .prose :global(a) {
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .prose :global(code) {
    font-family: var(--font-mono);
    font-size: 0.9em;
    background-color: var(--surface-raised, var(--bg));
    padding: 1px 4px;
  }

  .prose :global(pre) {
    font-family: var(--font-mono);
    font-size: 13px;
    background-color: var(--surface-raised, var(--bg));
    padding: var(--space-4, 16px);
    overflow-x: auto;
    margin-bottom: var(--space-4, 16px);
    border-left: 2px solid var(--border);
  }

  .prose :global(pre code) {
    background: none;
    padding: 0;
  }

  .prose :global(blockquote) {
    border-left: 2px solid var(--border);
    padding-left: var(--space-4, 16px);
    margin: 0 0 var(--space-4, 16px);
    color: var(--text-muted);
    font-style: italic;
  }

  .prose :global(ul),
  .prose :global(ol) {
    padding-left: var(--space-5, 24px);
    margin-bottom: var(--space-4, 16px);
  }

  .prose :global(li) {
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.70);
    color: var(--text);
    list-style: disc;
  }

  .prose :global(ol li) {
    list-style: decimal;
  }

  .prose :global(hr) {
    border: none;
    border-top: 1px solid var(--border);
    margin: var(--space-6, 32px) 0;
  }

  .status {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-muted);
  }

  .status.error {
    color: #c0392b;
  }

  @media (max-width: 640px) {
    .title-row {
      flex-direction: column;
    }

    .mode-toggle {
      width: 100%;
    }

    .note-body {
      padding: var(--space-4, 16px);
    }
  }
</style>
