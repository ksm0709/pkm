<script lang="ts">
  import EgoConstellation from '$lib/components/EgoConstellation.svelte';

  interface Neighbor {
    note_id: string;
    title: string;
    type: string;
    confidence?: number;
  }

  interface NeighborData {
    note_id: string;
    outbound: Neighbor[];
    inbound: Neighbor[];
    semantic: Neighbor[];
  }

  interface Props {
    vaultName: string;
    data: NeighborData | null;
    loading?: boolean;
  }

  let { vaultName, data, loading = false }: Props = $props();

  /** Parse YYYY-MM-DD prefix from note_id if present. */
  function parseDate(note_id: string): string | null {
    const m = note_id.match(/^(\d{4}-\d{2}-\d{2})/);
    return m ? m[1] : null;
  }

  /** Derive a short filename from note_id. */
  function toFilename(note_id: string): string {
    return `${note_id}.md`;
  }

  interface Group {
    label: string;
    items: Neighbor[];
  }

  let groups = $derived<Group[]>(
    data
      ? [
          { label: 'OUTBOUND', items: data.outbound },
          { label: 'SEMANTIC', items: data.semantic },
          { label: 'INBOUND', items: data.inbound }
        ].filter((g) => g.items.length > 0)
      : []
  );
</script>

{#if !loading && data && groups.length > 0}
  <aside class="neighbor-panel">
    <div class="divider" aria-hidden="true">
      <span class="divider-label">SIGNAL ANALYZER</span>
    </div>

    <div class="panel-body">
      <div class="constellation-shell">
        <EgoConstellation {vaultName} noteId={data.note_id} />
      </div>

      {#each groups as group (group.label)}
        <section class="group">
          <p class="group-label">{group.label}</p>
          <ul class="neighbor-list">
            {#each group.items as neighbor (neighbor.note_id)}
              {@const date = parseDate(neighbor.note_id)}
              {@const filename = toFilename(neighbor.note_id)}
              <li class="neighbor-item">
                <a href="/{vaultName}/notes/{neighbor.note_id}" class="neighbor-link">
                  <span class="neighbor-title">{neighbor.title || neighbor.note_id}</span>
                  <span class="neighbor-meta">
                    {#if date}
                      {date} · {filename}
                    {:else}
                      {filename}
                    {/if}
                  </span>
                  {#if neighbor.confidence !== undefined}
                    <span class="confidence">{neighbor.confidence.toFixed(2)}</span>
                  {/if}
                </a>
              </li>
            {/each}
          </ul>
        </section>
      {/each}
    </div>
  </aside>
{/if}

<style>
  .neighbor-panel {
    margin-top: var(--space-7, 48px);
  }

  .divider {
    display: flex;
    align-items: center;
    gap: var(--space-3, 12px);
    margin-bottom: var(--space-6, 32px);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-faint);
  }

  .divider::after {
    content: "";
    height: 1px;
    flex: 1;
    background: linear-gradient(90deg, var(--accent), var(--border));
  }

  .panel-body {
    display: flex;
    flex-direction: column;
    gap: var(--space-5, 24px);
  }

  .constellation-shell {
    border-left: 1px solid var(--border);
    padding-left: var(--space-4, 16px);
  }

  .group {
    border-left: 1px solid var(--accent);
    padding-left: var(--space-4, 16px);
  }

  .group-label {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: var(--type-chrome-sm-weight, 500);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-faint);
    margin: 0 0 var(--space-2, 8px);
  }

  .neighbor-list {
    display: flex;
    flex-direction: column;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .neighbor-item {
    border-top: 1px solid var(--border);
  }

  .neighbor-link {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(120px, auto) auto;
    gap: var(--space-3, 12px);
    align-items: center;
    min-height: 40px;
    font-family: var(--font-mono);
    font-size: 14px;
    color: var(--text);
    text-decoration: none;
    border-left: 2px solid transparent;
    padding: 0 var(--space-2, 8px);
    transition: color var(--dur-fast, 120ms) var(--ease-out), background-color var(--dur-fast, 120ms) var(--ease-out), border-color var(--dur-fast, 120ms) var(--ease-out);
  }

  .neighbor-link:hover,
  .neighbor-link:focus-visible {
    color: var(--accent);
    background: var(--accent-bg);
    border-left-color: var(--accent);
    outline: none;
  }

  .neighbor-title,
  .neighbor-meta {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .confidence {
    font-size: 11px;
    color: var(--accent);
    border: 1px solid var(--border);
    padding: 1px 5px;
  }

  .neighbor-meta {
    font-size: 12px;
    color: var(--text-muted);
  }

  @media (max-width: 640px) {
    .neighbor-link {
      grid-template-columns: 1fr auto;
      min-height: 54px;
      padding-block: var(--space-2, 8px);
    }

    .neighbor-meta {
      grid-column: 1 / -1;
    }
  }
</style>
