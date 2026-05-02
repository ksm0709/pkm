<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { apiGet } from '$lib/api/client.js';

  interface NoteEntry {
    note_id: string;
    title: string;
    path: string;
    tags: string[];
    created_at: string | null;
  }

  let notes = $state<NoteEntry[]>([]);
  let loading = $state(true);
  let error = $state('');

  let vaultName = $derived($page.params.vault);

  onMount(async () => {
    try {
      notes = await apiGet<NoteEntry[]>(`/api/v1/vault/${vaultName}/notes`);
      // Store last visited vault
      localStorage.setItem('pkm.lastVault', vaultName);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load notes.';
    } finally {
      loading = false;
    }
  });
</script>

<svelte:head>
  <title>{vaultName} — pkm</title>
</svelte:head>

<main class="reading-column vault-home">
  <h1>{vaultName}</h1>

  {#if loading}
    <p class="status-msg">Loading…</p>
  {:else if error}
    <p class="status-msg error">{error}</p>
  {:else if notes.length === 0}
    <p class="status-msg faint">No notes found.</p>
  {:else}
    <ul class="note-list">
      {#each notes as note (note.note_id)}
        <li class="note-entry">
          <a href="/{vaultName}/notes/{note.note_id}" class="note-link">
            {note.title || note.note_id}
          </a>
          {#if note.created_at}
            <span class="note-meta">{note.created_at}</span>
          {/if}
          {#if note.tags?.length}
            <span class="note-tags">{note.tags.map((t) => `#${t}`).join(' ')}</span>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</main>

<style>
  .vault-home {
    padding-top: var(--space-6, 32px);
    padding-bottom: var(--space-8, 64px);
  }

  h1 {
    font-family: var(--font-display);
    font-size: var(--type-h1-size, 28px);
    font-weight: var(--type-h1-weight, 600);
    color: var(--text);
    margin-bottom: var(--space-5, 24px);
  }

  .note-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 12px);
  }

  .note-entry {
    display: flex;
    align-items: baseline;
    gap: var(--space-3, 12px);
    font-family: var(--font-mono);
  }

  .note-link {
    font-size: var(--type-chrome-size, 13px);
    color: var(--text);
    text-decoration: none;
  }

  .note-link:hover {
    color: var(--accent);
  }

  .note-meta {
    font-size: 12px;
    color: var(--text-muted);
    flex-shrink: 0;
  }

  .note-tags {
    font-size: 12px;
    color: var(--text-faint);
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
</style>
