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
    <!-- Hairline divider with centered Newsreader Italic · glyph -->
    <div class="divider" aria-hidden="true">
      <span class="divider-dot">·</span>
    </div>

    <div class="panel-body">
      <!-- EgoConstellation: 2-hop radial SVG — above first group, unique to NeighborPanel -->
      <EgoConstellation {vaultName} noteId={data.note_id} />

      {#each groups as group (group.label)}
        <section class="group">
          <p class="group-label">
            {group.label}
          </p>
          <ul class="neighbor-list">
            {#each group.items as neighbor (neighbor.note_id)}
              {@const date = parseDate(neighbor.note_id)}
              {@const filename = toFilename(neighbor.note_id)}
              <li class="neighbor-item">
                <a
                  href="/{vaultName}/notes/{neighbor.note_id}"
                  class="neighbor-title"
                >
                  {neighbor.title || neighbor.note_id}
                  {#if neighbor.confidence !== undefined}
                    <span class="confidence">{neighbor.confidence.toFixed(2)}</span>
                  {/if}
                </a>
                <p class="neighbor-meta">
                  {#if date}
                    {date} · {filename}
                  {:else}
                    {filename}
                  {/if}
                </p>
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
    /* No box, no border on the panel itself */
  }

  /* Hairline divider: 1px var(--border) with centered Newsreader Italic · */
  .divider {
    position: relative;
    border-top: 1px solid var(--border);
    margin-bottom: var(--space-6, 32px);
    text-align: center;
  }

  .divider-dot {
    display: inline-block;
    position: relative;
    top: -0.7em; /* negative margin-top equivalent — overlaps the hairline */
    background-color: var(--bg);
    padding: 0 var(--space-2, 8px);
    font-family: var(--font-display);
    font-style: italic;
    font-size: 18px;
    color: var(--text-faint);
    line-height: 1;
  }

  /* Panel body indented var(--space-7) from body — asymmetric rail */
  .panel-body {
    padding-left: var(--space-7, 48px);
    display: flex;
    flex-direction: column;
    gap: var(--space-5, 24px);
  }

  .group {
    display: flex;
    flex-direction: column;
    gap: var(--space-2, 8px);
  }

  /* Group labels: Plex Mono 11px uppercase letter-spacing 0.08em --text-faint */
  .group-label {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: var(--type-chrome-sm-weight, 500);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-faint);
    margin: 0;
  }

  .neighbor-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 12px);
  }

  .neighbor-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  /* Titles: Plex Mono 14px --text, linkified --accent on hover */
  .neighbor-title {
    font-family: var(--font-mono);
    font-size: 14px;
    color: var(--text);
    text-decoration: none;
    display: flex;
    align-items: baseline;
    gap: var(--space-2, 8px);
  }

  .neighbor-title:hover {
    color: var(--accent);
  }

  .confidence {
    font-size: 12px;
    color: var(--text-faint);
  }

  /* Date · filename: Plex Mono 12px --text-muted */
  .neighbor-meta {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-muted);
    margin: 0;
  }
</style>
