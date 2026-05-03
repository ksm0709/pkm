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
  let loadedAt = $state<string | null>(null);

  let vaultName = $derived($page.params.vault);
  const topTags = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const note of notes) {
      for (const tag of note.tags ?? []) {
        counts.set(tag, (counts.get(tag) ?? 0) + 1);
      }
    }
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 8);
  });

  onMount(async () => {
    try {
      notes = await apiGet<NoteEntry[]>(`/api/v1/vault/${vaultName}/notes`);
      loadedAt = new Intl.DateTimeFormat(undefined, {
        hour: '2-digit',
        minute: '2-digit'
      }).format(new Date());
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

<main class="vault-home">
  <header class="ops-header">
    <p class="eyebrow">VAULT OPERATIONS</p>
    <div class="title-row">
      <h1>{vaultName}</h1>
      <div class="status-stack" aria-label="Vault status">
        <span>{notes.length} notes</span>
        {#if loadedAt}
          <span>loaded {loadedAt}</span>
        {/if}
      </div>
    </div>
  </header>

  {#if loading}
    <p class="status-msg">Loading…</p>
  {:else if error}
    <p class="status-msg error">{error}</p>
  {:else if notes.length === 0}
    <p class="status-msg faint">No notes found.</p>
  {:else}
    <div class="ops-grid">
      <section class="ledger" aria-label="Notes ledger">
        <div class="ledger-head">
          <span>NOTE</span>
          <span>PATH</span>
          <span>TAGS</span>
        </div>
        <ul class="note-list">
          {#each notes as note (note.note_id)}
            <li class="note-entry">
              <a href="/{vaultName}/notes/{note.note_id}" class="note-link">
                <span class="note-title">{note.title || note.note_id}</span>
                <span class="note-path">{note.path || note.note_id}</span>
                <span class="note-tags">
                  {note.tags?.length ? note.tags.map((t) => `#${t}`).join(' ') : '—'}
                </span>
              </a>
            </li>
          {/each}
        </ul>
      </section>

      {#if topTags.length}
        <aside class="status-lane" aria-label="Tag summary">
          <p class="lane-label">SIGNALS</p>
          <ul class="tag-list">
            {#each topTags as [tag, count] (tag)}
              <li>
                <span>#{tag}</span>
                <strong>{count}</strong>
              </li>
            {/each}
          </ul>
        </aside>
      {/if}
    </div>
  {/if}
</main>

<style>
  .vault-home {
    width: min(1180px, calc(100vw - 64px));
    margin: 0 auto;
    padding: var(--space-6, 32px) 0 var(--space-8, 64px);
  }

  .ops-header {
    border-left: 1px solid var(--accent);
    padding-left: var(--space-4, 16px);
    margin-bottom: var(--space-6, 32px);
  }

  .eyebrow,
  .ledger-head,
  .lane-label {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-faint);
    margin: 0;
  }

  .title-row {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: var(--space-5, 24px);
    margin-top: var(--space-2, 8px);
  }

  h1 {
    font-family: var(--font-display);
    font-size: clamp(34px, 5vw, 44px);
    line-height: 1;
    font-weight: var(--type-h1-weight, 600);
    color: var(--text);
    margin: 0;
  }

  .status-stack {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 4px;
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .ops-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(180px, 260px);
    gap: var(--space-6, 32px);
    align-items: start;
  }

  .ledger {
    border-top: 1px solid var(--border);
  }

  .ledger-head {
    display: grid;
    grid-template-columns: minmax(180px, 1.1fr) minmax(160px, 0.9fr) minmax(120px, 0.8fr);
    gap: var(--space-4, 16px);
    min-height: 34px;
    align-items: center;
    border-bottom: 1px solid var(--border);
  }

  .note-list {
    display: flex;
    flex-direction: column;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .note-entry {
    border-bottom: 1px solid var(--border);
  }

  .note-link {
    display: grid;
    grid-template-columns: minmax(180px, 1.1fr) minmax(160px, 0.9fr) minmax(120px, 0.8fr);
    gap: var(--space-4, 16px);
    align-items: center;
    min-height: 40px;
    font-size: var(--type-chrome-size, 13px);
    color: var(--text);
    text-decoration: none;
    font-family: var(--font-mono);
    border-left: 2px solid transparent;
    padding: 0 var(--space-3, 12px);
    transition: color var(--dur-fast, 120ms) var(--ease-out), background-color var(--dur-fast, 120ms) var(--ease-out), border-color var(--dur-fast, 120ms) var(--ease-out);
  }

  .note-link:hover,
  .note-link:focus-visible {
    color: var(--accent);
    background: var(--accent-bg);
    border-left-color: var(--accent);
    outline: none;
  }

  .note-title,
  .note-path,
  .note-tags {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .note-path {
    font-size: var(--type-chrome-sm-size, 11px);
    color: var(--text-muted);
  }

  .note-tags {
    font-size: var(--type-chrome-sm-size, 11px);
    color: var(--text-faint);
  }

  .status-lane {
    border-left: 1px solid var(--border);
    padding-left: var(--space-4, 16px);
  }

  .tag-list {
    list-style: none;
    margin: var(--space-3, 12px) 0 0;
    padding: 0;
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
  }

  .tag-list li {
    display: flex;
    justify-content: space-between;
    gap: var(--space-3, 12px);
    min-height: 34px;
    align-items: center;
    border-bottom: 1px solid var(--border);
    color: var(--text-muted);
  }

  .tag-list strong {
    color: var(--accent);
    font-weight: 500;
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

  @media (max-width: 760px) {
    .vault-home {
      width: auto;
      padding-inline: var(--space-4, 16px);
    }

    .title-row,
    .ops-grid {
      display: block;
    }

    .status-stack {
      align-items: flex-start;
      margin-top: var(--space-3, 12px);
    }

    .status-lane {
      margin-top: var(--space-6, 32px);
    }

    .ledger-head {
      display: none;
    }

    .note-link {
      grid-template-columns: 1fr;
      gap: 3px;
      min-height: 56px;
      align-items: center;
      padding-block: var(--space-2, 8px);
    }
  }
</style>
