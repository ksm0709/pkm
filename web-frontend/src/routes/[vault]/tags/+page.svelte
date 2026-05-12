<script lang="ts">
  import { page } from "$app/stores";
  import { apiGet } from "$lib/api/client.js";

  interface TagEntry {
    tag: string;
    count: number;
  }

  interface TagsResponse {
    tags: TagEntry[];
    count: number;
  }

  let tags = $state<TagEntry[]>([]);
  let loading = $state(true);
  let error = $state("");
  let loadedAt = $state<string | null>(null);
  let loadToken = 0;

  let vaultName = $derived($page.params.vault);

  async function loadTags(vault: string) {
    const token = ++loadToken;
    tags = [];
    loading = true;
    error = "";
    loadedAt = null;

    try {
      const data = await apiGet<TagsResponse>(
        `/api/v1/vault/${encodeURIComponent(vault)}/tags`,
      );
      if (token !== loadToken) return;
      tags = sortTags(data.tags ?? []);
      loadedAt = new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date());
    } catch (e) {
      if (token !== loadToken) return;
      error = e instanceof Error ? e.message : "Failed to load tags.";
    } finally {
      if (token !== loadToken) return;
      loading = false;
    }
  }

  $effect(() => {
    if (!vaultName) return;
    void loadTags(vaultName);
  });

  function sortTags(entries: TagEntry[]) {
    return [...entries].sort(
      (a, b) => b.count - a.count || a.tag.localeCompare(b.tag),
    );
  }

  function tagHref(tag: string) {
    return `/${encodeURIComponent(vaultName)}/notes/${encodeURIComponent(`tag:${tag}`)}`;
  }
</script>

<svelte:head>
  <title>{vaultName} tags — pkm</title>
</svelte:head>

<main class="tags-page">
  <header class="tags-header">
    <div class="status-stack" aria-label="Tags status">
      <span>{tags.length} tags</span>
      {#if loadedAt}
        <span>loaded {loadedAt}</span>
      {/if}
    </div>
  </header>

  {#if loading}
    <p class="status-msg">Loading…</p>
  {:else if error}
    <p class="status-msg error">{error}</p>
  {:else if tags.length === 0}
    <p class="status-msg faint">No tags found.</p>
  {:else}
    <section class="tag-ledger" aria-label="Tags ledger">
      <div class="tag-ledger-head">
        <span>TAG</span>
        <span>REFERENCES</span>
      </div>
      <ul class="tag-list">
        {#each tags as tag (tag.tag)}
          <li class="tag-entry">
            <a class="tag-link" href={tagHref(tag.tag)}>
              <span class="tag-name">#{tag.tag}</span>
              <span class="tag-count">{tag.count}</span>
            </a>
          </li>
        {/each}
      </ul>
    </section>
  {/if}
</main>

<style>
  .tags-page {
    width: min(860px, calc(100vw - 64px));
    margin: 0 auto;
    padding: var(--space-6, 32px) 0 var(--space-8, 64px);
  }

  .tags-header {
    display: flex;
    justify-content: flex-end;
    margin-bottom: var(--space-6, 32px);
  }

  .status-stack,
  .tag-ledger-head,
  .tag-link,
  .status-msg {
    font-family: var(--font-mono);
  }

  .status-stack {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 4px;
    font-size: var(--type-chrome-sm-size, 11px);
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .tag-ledger {
    border-top: 1px solid var(--border);
  }

  .tag-ledger-head {
    display: grid;
    grid-template-columns: minmax(180px, 1fr) 120px;
    gap: var(--space-4, 16px);
    min-height: 34px;
    align-items: center;
    border-bottom: 1px solid var(--border);
    font-size: var(--type-chrome-sm-size, 11px);
    color: var(--text-faint);
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  .tag-ledger-head span:last-child {
    text-align: right;
  }

  .tag-list {
    display: flex;
    flex-direction: column;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .tag-entry {
    border-bottom: 1px solid var(--border);
  }

  .tag-link {
    display: grid;
    grid-template-columns: minmax(180px, 1fr) 120px;
    gap: var(--space-4, 16px);
    align-items: center;
    min-height: 44px;
    padding: 0 var(--space-3, 12px);
    border-left: 2px solid transparent;
    color: var(--text);
    text-decoration: none;
    transition:
      color var(--dur-fast, 120ms) var(--ease-out),
      background-color var(--dur-fast, 120ms) var(--ease-out),
      border-color var(--dur-fast, 120ms) var(--ease-out);
  }

  .tag-link:hover,
  .tag-link:focus-visible {
    color: var(--accent);
    background: var(--accent-bg);
    border-left-color: var(--accent);
    outline: none;
  }

  .tag-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tag-count {
    color: var(--accent);
    text-align: right;
    font-weight: 600;
  }

  .status-msg {
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
    .tags-page {
      width: auto;
      padding-inline: var(--space-4, 16px);
    }

    .tags-header {
      justify-content: flex-start;
    }

    .status-stack {
      align-items: flex-start;
    }

    .tag-ledger-head {
      display: none;
    }

    .tag-link {
      grid-template-columns: minmax(0, 1fr) auto;
      min-height: 48px;
    }
  }
</style>
