<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { apiGet } from '$lib/api/client.js';
  import {
    type NormalizedEdge,
    type NormalizedGraph,
    type NormalizedNode,
    degreesByNode,
    filterEdges,
    filterNodes,
    normalizeGraph
  } from '$lib/graph/normalize';

  type VizMode = 'Radial' | 'Cluster' | 'Degree' | 'List';
  type NodeFilter = 'all' | 'note' | 'tag';
  type EdgeFilter = 'all' | 'wikilink' | 'has_tag' | 'semantic_similar';

  interface PositionedNode extends NormalizedNode {
    x: number;
    y: number;
  }

  interface PositionedEdge {
    id: string;
    source: string;
    target: string;
    x1: number;
    y1: number;
    x2: number;
    y2: number;
    type?: string;
  }

  const GRAPH_VISUAL_CAP = 120;
  const VIEW_WIDTH = 1040;
  const VIEW_HEIGHT = 540;
  const MARGIN = 24;

  let vaultName = $derived($page.params.vault);
  let loading = $state(true);
  let error = $state('');
  let graph = $state<NormalizedGraph | null>(null);
  let mode = $state<VizMode>('Radial');
  let nodeFilter = $state<NodeFilter>('all');
  let edgeFilter = $state<EdgeFilter>('all');
  let loadToken = 0;

  let loadLabel = $derived(graph ? graph.nodes.length.toString() : '0');

  async function load(vault: string) {
    const token = ++loadToken;
    loading = true;
    error = '';
    graph = null;

    try {
      const payload = await apiGet(`/api/v1/vault/${encodeURIComponent(vault)}/graph`);
      if (token !== loadToken) return;
      graph = normalizeGraph(payload as unknown as Record<string, unknown>);
    } catch (cause) {
      if (token !== loadToken) return;
      error =
        cause instanceof Error && cause.message.includes('404')
          ? 'Graph data unavailable. Run `pkm index` to generate graph data.'
          : cause instanceof Error
            ? cause.message
            : 'Failed to load graph.';
    } finally {
      if (token !== loadToken) return;
      loading = false;
    }
  }

  $effect(() => {
    if (!vaultName) return;
    void load(vaultName);
  });

  const normalizedNodeFilters: NodeFilter[] = ['all', 'note', 'tag'];
  const normalizedEdgeFilters: EdgeFilter[] = ['all', 'wikilink', 'has_tag', 'semantic_similar'];

  const vizModes: VizMode[] = ['Radial', 'Cluster', 'Degree', 'List'];

  const modeTag = $derived(`mode:${mode}`);

  const filteredNodes = $derived(filterNodes(graph?.nodes ?? [], nodeFilter));
  const filteredEdges = $derived(filterEdges(graph?.edges ?? [], edgeFilter));

  const withDegree = $derived(() => {
    if (!graph) return new Map<string, number>();
    return degreesByNode(filteredNodes, filteredEdges);
  });

  const nodeDegreePairs = $derived<PositionedNode[]>(() => {
    if (!graph) return [];

    const nodes = [...filteredNodes];
    const countById = withDegree;

    let ordered = nodes;
    if (mode === 'Degree') {
      ordered = [...nodes].sort((a, b) => {
        const diff = countById.get(b.id)! - countById.get(a.id)!;
        if (diff !== 0) return diff;
        return a.id.localeCompare(b.id);
      });
    }

    if (mode === 'Cluster') {
      ordered = [...nodes].sort((a, b) => {
        const ca = a.community || a.cluster || 'zz-other';
        const cb = b.community || b.cluster || 'zz-other';
        const diff = ca.localeCompare(cb);
        return diff !== 0 ? diff : a.id.localeCompare(b.id);
      });
    }

    if (mode === 'Radial' || mode === 'Cluster' || mode === 'Degree') {
      return ordered.map((node, index) => {
        const radius = Math.min(VIEW_WIDTH, VIEW_HEIGHT) / 2 - MARGIN;
        const angle = (Math.PI * 2 * index) / Math.max(ordered.length, 1) - Math.PI / 2;
        const r = radius;
        const cx = VIEW_WIDTH / 2 + r * Math.cos(angle);
        const cy = VIEW_HEIGHT / 2 + r * Math.sin(angle);
        return { ...node, x: cx, y: cy };
      });
    }

    return ordered.map((node) => ({
      ...node,
      x: VIEW_WIDTH / 2,
      y: VIEW_HEIGHT / 2
    }));
  });

  const filteredVisualNodes = $derived<PositionedNode[]>(
    mode === 'List'
      ? []
      : nodeDegreePairs.slice(0, GRAPH_VISUAL_CAP)
  );

  const filteredVisualEdges = $derived<PositionedEdge[]>(() => {
    if (!filteredVisualNodes.length) return [];

    const nodeSet = new Set(filteredVisualNodes.map((node) => node.id));
    const posMap = new Map(filteredVisualNodes.map((node) => [node.id, node] as const));

    return filteredEdges
      .map((edge) => {
        const source = posMap.get(edge.source);
        const target = posMap.get(edge.target);
        if (!source || !target) return null;
        return {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          type: edge.type,
          x1: source.x,
          y1: source.y,
          x2: target.x,
          y2: target.y
        } satisfies PositionedEdge;
      })
      .filter((edge): edge is PositionedEdge => edge !== null)
      .slice(0, GRAPH_VISUAL_CAP);
  });

  const missingFiltered = $derived(
    mode === 'List'
      ? filteredNodes.length === 0
      : filteredVisualNodes.length === 0
  );

  function goNode(node: NormalizedNode) {
    if (node.type !== 'note') return;
    void goto(`/${vaultName}/notes/${encodeURIComponent(node.id)}`);
  }

  function nodeColor(node: NormalizedNode) {
    if (node.type === 'tag') return 'var(--tag)';
    if (node.type === 'note_or_unresolved') return 'var(--text-muted)';
    return 'var(--text-primary)';
  }
</script>

<svelte:head>
  <title>{vaultName} — graph — pkm</title>
</svelte:head>

<main class="graph-page">
  <header class="ops-header">
    <div class="title-row">
      <div>
        <h1 class="page-title">Graph</h1>
        <p class="vault-subtitle">Visual overviews with filter and navigation</p>
      </div>
      <div class="summary" aria-live="polite">{loadLabel} nodes</div>
    </div>
  </header>

  {#if loading}
    <p class="status-msg">Loading graph…</p>
  {:else if error}
    <div class="empty-state">
      <p>{error}</p>
    </div>
  {:else}
    <section class="controls" aria-label="Graph controls">
      <label>
        <span>Visualization</span>
        <div class="segmented" role="group" aria-label="Visualization mode">
          {#each vizModes as item (item)}
            <button
              type="button"
              data-mode={item}
              aria-pressed={item === mode}
              class:active={item === mode}
              onclick={() => (mode = item)}
            >
              {item}
            </button>
          {/each}
        </div>
      </label>

      <label>
        <span>Node type</span>
        <select
          aria-label="Node type filter"
          bind:value={nodeFilter}
        >
          <option value="all">All</option>
          <option value="note">Note</option>
          <option value="tag">Tag</option>
        </select>
      </label>

      <label>
        <span>Edge type</span>
        <select aria-label="Edge type filter" bind:value={edgeFilter}>
          {#each normalizedEdgeFilters as item (item)}
            <option value={item}>{item === 'all' ? 'All' : item}</option>
          {/each}
        </select>
      </label>

      <p class="status-mini">mode: {modeTag}</p>
      {#if mode !== 'List' && graph && graph.nodes.length > GRAPH_VISUAL_CAP}
        <p class="status-mini" data-cap-status>
          rendering first {GRAPH_VISUAL_CAP} of {graph.nodes.length} nodes
        </p>
      {/if}
    </section>

    {#if filteredEdges.length + filteredNodes.length === 0}
      <p class="status-msg">No matches.</p>
    {:else if nodeFilter === 'tag' && filteredNodes.length > 0}
      {#if mode === 'List'}
        <p class="status-mini">Showing tags only.</p>
      {/if}
    {/if}

    {#if mode === 'List'}
      <section class="graph-table" aria-label="Graph list">
        <div class="list-head">
          <span>Node</span>
          <span>Type</span>
          <span>Description</span>
        </div>
        {#each filteredNodes as item (item.id)}
          <article class="list-row">
            <a
              class="node-link"
              href={item.type === 'note' ? `/${vaultName}/notes/${encodeURIComponent(item.id)}` : '#'}
              onclick={(event) => {
                if (item.type !== 'note') event.preventDefault();
              }}
            >
              {item.title}
            </a>
            <span>{item.type}</span>
            <span class="muted">{item.description || '—'}</span>
          </article>
        {/each}
      </section>
    {:else if missingFiltered}
      <p class="status-msg">No nodes visible under current filters.</p>
    {:else}
      <section>
        <p class="status-mini" data-testid="graph-summary">
          {filteredNodes.length} nodes · {filteredEdges.length} edges
        </p>
        <div class="graph-shell">
          <svg
            width={VIEW_WIDTH}
            height={VIEW_HEIGHT}
            viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
            class="graph-canvas"
            aria-label="graph overview"
          >
            {#each filteredVisualEdges as edge (edge.id)}
              <line
                data-testid="graph-edge"
                class="graph-edge"
                x1={edge.x1}
                y1={edge.y1}
                x2={edge.x2}
                y2={edge.y2}
                stroke-width="1"
                data-source={edge.source}
                data-target={edge.target}
                data-edge-type={edge.type}
              />
            {/each}

            {#each filteredVisualNodes as node (node.id)}
              <g
                class="graph-node"
                role="button"
                tabindex="0"
                data-testid="graph-node"
                data-node-id={node.id}
                data-node-type={node.type}
                onclick={() => goNode(node)}
                onkeydown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    goNode(node);
                  }
                }}
              >
                <circle cx={node.x} cy={node.y} r="4" fill={nodeColor(node)}></circle>
                <text x={node.x + 8} y={node.y + 4} fill="var(--text-primary)">{node.title}</text>
              </g>
            {/each}
          </svg>
        </div>
      </section>
    {/if}
  {/if}
</main>

<style>
  .graph-page {
    width: min(1200px, calc(100vw - 64px));
    margin: 0 auto;
    padding: var(--space-6, 32px) 0 var(--space-8, 64px);
  }

  .ops-header {
    margin-bottom: var(--space-5, 20px);
  }

  .title-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: var(--space-4, 16px);
  }

  .page-title {
    margin: 0;
    font-size: var(--type-title-size, 28px);
  }

  .vault-subtitle {
    margin: 6px 0 0;
    color: var(--text-muted);
  }

  .summary {
    font-family: var(--font-mono);
    color: var(--text-faint);
    text-transform: uppercase;
  }

  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 18px;
    align-items: end;
    margin-bottom: 16px;
  }

  .controls label {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-family: var(--font-mono);
    color: var(--text-faint);
    font-size: 11px;
  }

  .segmented {
    display: inline-flex;
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }

  .segmented button {
    border: 0;
    background: transparent;
    padding: 6px 10px;
    color: var(--text-muted);
    cursor: pointer;
  }

  .segmented button.active {
    background: var(--surface-2, var(--surface));
    color: var(--text-primary);
  }

  .status-mini {
    margin: 0;
    color: var(--text-muted);
  }

  .status-msg {
    color: var(--text-muted);
  }

  .empty-state {
    color: var(--text-faint);
  }

  .graph-shell {
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px;
  }

  .graph-canvas {
    display: block;
    min-width: min(100%, 1040px);
  }

  .graph-edge {
    stroke: var(--border);
    stroke-opacity: 0.8;
  }

  .graph-node {
    cursor: pointer;
  }

  .graph-node text {
    font-size: 11px;
    pointer-events: none;
    fill: var(--text-muted);
  }

  .graph-table {
    border-top: 1px solid var(--border);
    display: grid;
    grid-template-columns: minmax(0, 2fr) 160px minmax(0, 2fr);
    gap: 0;
    font-size: 14px;
  }

  .list-head {
    display: contents;
    font-family: var(--font-mono);
    color: var(--text-faint);
    text-transform: uppercase;
    font-size: 11px;
  }

  .list-row {
    display: contents;
    border-bottom: 1px solid var(--border);
    min-height: 32px;
  }

  .list-row span,
  .list-row a {
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
    display: block;
  }

  .node-link {
    color: var(--text-primary);
  }

  .muted {
    color: var(--text-muted);
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
</style>
