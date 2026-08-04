<script lang="ts">
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import { apiClient, apiGet } from "$lib/api/client.js";
  import { rememberVault } from "$lib/vault/remembered-vault";

  interface NoteEntry {
    note_id: string;
    title: string;
    path: string;
    description?: string | null;
    tags: string[];
    created_at: string | null;
    updated_at?: string | null;
    modified_at?: string | null;
  }

  let notes = $state<NoteEntry[]>([]);
  let loading = $state(true);
  let creatingNote = $state(false);
  let error = $state("");
  let loadedAt = $state<string | null>(null);

  let vaultName = $derived($page.params.vault);
  let loadToken = 0;
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

  async function loadNotes(vault: string) {
    const token = ++loadToken;
    notes = [];
    loading = true;
    error = "";
    loadedAt = null;

    try {
      const loadedNotes = await apiGet<NoteEntry[]>(
        `/api/v1/vault/${vault}/notes`,
      );
      if (token !== loadToken) return;
      notes = sortNotesByRecentModification(loadedNotes);
      loadedAt = new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date());
      rememberVault(vault);
    } catch (e) {
      if (token !== loadToken) return;
      error = e instanceof Error ? e.message : "Failed to load notes.";
    } finally {
      if (token !== loadToken) return;
      loading = false;
    }
  }

  async function createNote() {
    if (creatingNote) return;
    const title =
      typeof window !== "undefined" ? window.prompt("Note title") : null;
    if (!title?.trim()) return;

    creatingNote = true;
    error = "";
    try {
      const response = await apiClient(`/api/v1/vault/${vaultName}/notes`, {
        method: "POST",
        body: JSON.stringify({ title, body: "", tags: [] }),
      });
      if (response.status !== 201)
        throw new Error(`POST note -> ${response.status}`);
      const payload = (await response.json()) as { note_id?: string };
      if (!payload.note_id) throw new Error("POST note -> missing note_id");
      await goto(`/${vaultName}/notes/${payload.note_id}`);
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to create note.";
    } finally {
      creatingNote = false;
    }
  }

  $effect(() => {
    if (!vaultName) return;
    void loadNotes(vaultName);
  });

  function sortNotesByRecentModification(entries: NoteEntry[]) {
    return [...entries].sort(
      (a, b) =>
        noteTime(b) - noteTime(a) || noteLabel(a).localeCompare(noteLabel(b)),
    );
  }

  function noteTime(note: NoteEntry) {
    const raw = note.modified_at ?? note.updated_at ?? note.created_at;
    if (!raw) return 0;
    const time = Date.parse(raw);
    return Number.isFinite(time) ? time : 0;
  }

  function noteLabel(note: NoteEntry) {
    return note.title || note.note_id || "";
  }
</script>

<svelte:head>
  <title>{vaultName} — pkm</title>
</svelte:head>

<main class="vault-home">
  <header class="ops-header">
    <div class="title-row">
      <button
        type="button"
        class="add-note-button"
        aria-label="Add note"
        disabled={creatingNote}
        onclick={() => void createNote()}
      >
        {creatingNote ? "Creating…" : "Add note"}
      </button>
      <div class="status-stack" aria-label="Vault status">
        <span>{notes.length} notes</span>
        {#if loadedAt}
          <span>loaded {loadedAt}</span>
        {/if}
      </div>
    </div>
  </header>

  {#if error}
    <p class="status-msg error">{error}</p>
  {:else if loading}
    <p class="status-msg">Loading…</p>
  {:else if notes.length === 0}
    <p class="status-msg faint">No notes found.</p>
  {:else}
    <div class="ops-grid">
      <section class="ledger" aria-label="Notes ledger">
        <div class="ledger-head">
          <span>NOTE</span>
          <span>DESCRIPTION</span>
          <span>TAGS</span>
        </div>
        <ul class="note-list">
          {#each notes as note (note.note_id)}
            <li class="note-entry">
              <a href="/{vaultName}/notes/{note.note_id}" class="note-link">
                <span class="note-title">{note.title || note.note_id}</span>
                <span class="note-description">{note.description || "—"}</span>
                <span class="note-tags">
                  {note.tags?.length
                    ? note.tags.map((t) => `#${t}`).join(" ")
                    : "—"}
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
    width: var(--page-content-width);
    margin: 0 auto;
    padding: var(--space-6, 32px) 0 var(--space-8, 64px);
  }

  .ops-header {
    margin-bottom: var(--space-6, 32px);
  }

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

  .add-note-button {
    min-height: 32px;
    padding: 0 var(--space-3, 12px);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm, 2px);
    background: var(--surface-raised, var(--bg));
    color: var(--text);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    cursor: pointer;
  }

  .add-note-button:hover:not(:disabled),
  .add-note-button:focus-visible {
    border-color: var(--accent);
    color: var(--accent);
    outline: none;
  }

  .add-note-button:disabled {
    cursor: wait;
    opacity: 0.7;
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
    grid-template-columns: minmax(180px, 1.1fr) minmax(160px, 0.9fr) minmax(
        120px,
        0.8fr
      );
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
    grid-template-columns: minmax(180px, 1.1fr) minmax(160px, 0.9fr) minmax(
        120px,
        0.8fr
      );
    gap: var(--space-4, 16px);
    align-items: center;
    min-height: 40px;
    font-size: var(--type-chrome-size, 13px);
    color: var(--text);
    text-decoration: none;
    font-family: var(--font-mono);
    border-left: 2px solid transparent;
    padding: 0 var(--space-3, 12px);
    transition:
      color var(--dur-fast, 120ms) var(--ease-out),
      background-color var(--dur-fast, 120ms) var(--ease-out),
      border-color var(--dur-fast, 120ms) var(--ease-out);
  }

  .note-link:hover,
  .note-link:focus-visible {
    color: var(--accent);
    background: var(--accent-bg);
    border-left-color: var(--accent);
    outline: none;
  }

  .note-title,
  .note-description,
  .note-tags {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .note-description {
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
