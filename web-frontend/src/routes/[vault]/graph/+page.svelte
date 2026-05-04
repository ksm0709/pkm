<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { apiClient } from '$lib/api/client.js';
  import {
    normalizeGraph,
    type NormalizedGraphEdge,
    type NormalizedGraphNode
  } from '$lib/graph/normalize.js';

  type GraphMode = 'Radial' | 'Cluster' | 'Degree' | 'List';
  type PositionedNode = NormalizedGraphNode & { x: number; y: number; groupLabel: string };
  type RenderedEdge = NormalizedGraphEdge & { x1: number; y1: number; x2: number; y2: number };

  let vaultName = $derived($page.params.vault ?? '');
  let loading = $state(true);
  let error = $state('');
  let missingGraph = $state(false);
  let rawGraph = $state<unknown>(null);
  let loadToken = 0;
  let mode = $state<GraphMode>('Radial');
  let nodeTypeFilter = $state('all');
  let edgeTypeFilter = $state('all');

  const VISUAL_NODE_CAP = 80;
  const W = 920;
  const H = 520;
  const CX = W / 2;
  const CY = H / 2;

  const graph = $derived(normalizeGraph(rawGraph));
  const filteredBaseNodes = $derived(
    graph.nodes.filter((node) => nodeTypeFilter === 'all' || node.type === nodeTypeFilter)
  );
  const filteredBaseNodeIds = $derived(new Set(filteredBaseNodes.map((node) => node.id)));
  const filteredEdges = $derived(
    graph.edges.filter(
      (edge) =>
        filteredBaseNodeIds.has(edge.source) &&
        filteredBaseNodeIds.has(edge.target) &&
        (edgeTypeFilter === 'all' || edge.type === edgeTypeFilter)
    )
  );
  const listNodes = $derived.by(() => {
    let nodes = filteredBaseNodes;
    if (edgeTypeFilter !== 'all') {
      const endpointIds = new Set(filteredEdges.flatMap((edge) => [edge.source, edge.target]));
      nodes = filteredBaseNodes.filter((node) => endpointIds.has(node.id));
    }
    if (mode === 'Degree') return [...nodes].sort(compareDegreeThenLabel);
    return [...nodes].sort(compareLabel);
  });
  const visibleNodes = $derived(positionNodes(listNodes.slice(0, VISUAL_NODE_CAP), mode));
  const visibleNodeIds = $derived(new Set(visibleNodes.map((node) => node.id)));
  const renderedEdges = $derived(renderEdges(filteredEdges, visibleNodes, visibleNodeIds));
  const clusterLabels = $derived.by(() => {
    const labels = new Set(visibleNodes.map((node) => node.groupLabel).filter(Boolean));
    return [...labels].slice(0, 8);
  });
  const capStatus = $derived(
    listNodes.length > VISUAL_NODE_CAP
      ? `Rendering first ${VISUAL_NODE_CAP} of ${listNodes.length} filtered nodes in the visual overview.`
      : ''
  );
  const noMatches = $derived(!loading && !error && graph.nodes.length > 0 && listNodes.length === 0);

  $effect(() => {
    if (!vaultName) return;
    void loadGraph(vaultName);
  });

  async function loadGraph(vault: string) {
    const token = ++loadToken;
    loading = true;
    error = '';
    missingGraph = false;
    rawGraph = null;

    try {
      const response = await apiClient(`/api/v1/vault/${encodeURIComponent(vault)}/graph`, {
        method: 'GET'
      });
      if (token !== loadToken) return;
      if (response.status === 404) {
        missingGraph = true;
        return;
      }
      if (!response.ok) throw new Error(`GET graph → ${response.status}`);
      rawGraph = await response.json();
    } catch (e) {
      if (token !== loadToken) return;
      error = e instanceof Error ? e.message : 'Failed to load graph.';
    } finally {
      if (token === loadToken) loading = false;
    }
  }

  function setMode(nextMode: GraphMode) {
    mode = nextMode;
  }

  function openNode(node: NormalizedGraphNode) {
    if (node.type !== 'note') return;
    void goto(`/${encodeURIComponent(vaultName)}/notes/${encodeURIComponent(node.id)}`);
  }

  function positionNodes(nodes: NormalizedGraphNode[], currentMode: GraphMode): PositionedNode[] {
    if (nodes.length === 0) return [];
    if (currentMode === 'Degree') return degreeLayout(nodes);
    if (currentMode === 'Cluster') return clusterLayout(nodes);
    return radialLayout(nodes);
  }

  function radialLayout(nodes: NormalizedGraphNode[]): PositionedNode[] {
    const radius = Math.min(W, H) * 0.38;
    return nodes.map((node, index) => {
      const angle = nodes.length === 1 ? -Math.PI / 2 : (2 * Math.PI * index) / nodes.length - Math.PI / 2;
      return {
        ...node,
        x: round(CX + radius * Math.cos(angle)),
        y: round(CY + radius * Math.sin(angle)),
        groupLabel: node.community || node.type
      };
    });
  }

  function clusterLayout(nodes: NormalizedGraphNode[]): PositionedNode[] {
    const groups = new Map<string, NormalizedGraphNode[]>();
    for (const node of nodes) {
      const key = node.community || node.type || 'unknown';
      groups.set(key, [...(groups.get(key) ?? []), node]);
    }
    const entries = [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    const centers = entries.map(([label], index) => {
      const angle = entries.length === 1 ? -Math.PI / 2 : (2 * Math.PI * index) / entries.length - Math.PI / 2;
      return {
        label,
        x: CX + 245 * Math.cos(angle),
        y: CY + 150 * Math.sin(angle)
      };
    });
    return entries.flatMap(([label, groupNodes], groupIndex) => {
      const center = centers[groupIndex];
      const radius = Math.min(84, 26 + groupNodes.length * 6);
      return groupNodes.map((node, index) => {
        const angle = groupNodes.length === 1 ? 0 : (2 * Math.PI * index) / groupNodes.length;
        return {
          ...node,
          x: round(center.x + radius * Math.cos(angle)),
          y: round(center.y + radius * Math.sin(angle)),
          groupLabel: label
        };
      });
    });
  }

  function degreeLayout(nodes: NormalizedGraphNode[]): PositionedNode[] {
    const ordered = [...nodes].sort(compareDegreeThenLabel);
    return ordered.map((node, index) => {
      const row = Math.floor(index / 10);
      const col = index % 10;
      return {
        ...node,
        x: round(80 + col * 84),
        y: round(80 + row * 56),
        groupLabel: `${node.degree} degree`
      };
    });
  }

  function renderEdges(
    edges: NormalizedGraphEdge[],
    nodes: PositionedNode[],
    nodeIds: Set<string>
  ): RenderedEdge[] {
    const positions = new Map(nodes.map((node) => [node.id, node]));
    return edges
      .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
      .flatMap((edge) => {
        const source = positions.get(edge.source);
        const target = positions.get(edge.target);
        return source && target
          ? [{ ...edge, x1: source.x, y1: source.y, x2: target.x, y2: target.y }]
          : [];
      });
  }

  function nodeRadius(node: NormalizedGraphNode) {
    return Math.min(16, 5 + node.degree * 1.5);
  }

  function typeClass(value: string) {
    return value.replace(/[^a-z0-9_-]/gi, '-').toLowerCase();
  }

  function round(value: number) {
    return Math.round(value * 10) / 10;
  }

  function compareLabel(a: NormalizedGraphNode, b: NormalizedGraphNode) {
    return a.label.localeCompare(b.label) || a.id.localeCompare(b.id);
  }

  function compareDegreeThenLabel(a: NormalizedGraphNode, b: NormalizedGraphNode) {
    return b.degree - a.degree || compareLabel(a, b);
  }
</script>

<svelte:head>
  <title>Graph — {vaultName} — pkm</title>
</svelte:head>

<main class="graph-page">
  <header class="graph-header">
    <div>
      <p class="eyebrow">VAULT GRAPH</p>
      <p class="graph-summary" data-testid="graph-summary">
        {#if loading}
          Loading graph…
        {:else if missingGraph || error}
          Graph unavailable
        {:else}
          <strong>{graph.nodes.length}</strong> {graph.nodes.length === 1 ? 'node' : 'nodes'} · <strong>{graph.edges.length}</strong> {graph.edges.length === 1 ? 'edge' : 'edges'}
        {/if}
      </p>
    </div>
    <div class="mode-switcher" aria-label="Graph mode">
      {#each ['Radial', 'Cluster', 'Degree', 'List'] as option (option)}
        <button
          type="button"
          class:active={mode === option}
          aria-pressed={mode === option}
          onclick={() => setMode(option as GraphMode)}
        >
          {option}
        </button>
      {/each}
    </div>
  </header>

  {#if loading}
    <p class="status-msg">Loading…</p>
  {:else if missingGraph}
    <section class="empty-state" aria-label="Missing graph index">
      <p class="empty-title">Graph index not found.</p>
      <p>Run <code>pkm index</code> for this vault, then reopen Graph to inspect the generated node-link map.</p>
    </section>
  {:else if error}
    <p class="status-msg error">{error}</p>
  {:else if graph.nodes.length === 0}
    <section class="empty-state" aria-label="Empty graph">
      <p class="empty-title">Graph is empty.</p>
      <p>Run <code>pkm index</code> after adding notes or links to populate the graph.</p>
    </section>
  {:else}
    <section class="graph-toolbar" aria-label="Graph filters">
      <label>
        <span>Node type</span>
        <select aria-label="Node type filter" bind:value={nodeTypeFilter}>
          <option value="all">All node types</option>
          {#each graph.nodeTypes as type (type)}
            <option value={type}>{type}</option>
          {/each}
        </select>
      </label>
      <label>
        <span>Edge type</span>
        <select aria-label="Edge type filter" bind:value={edgeTypeFilter}>
          <option value="all">All edge types</option>
          {#each graph.edgeTypes as type (type)}
            <option value={type}>{type}</option>
          {/each}
        </select>
      </label>
      <span class="mode-marker" data-testid="graph-mode">Mode: {mode}</span>
    </section>

    {#if noMatches}
      <p class="status-msg faint">No graph matches for the current filters.</p>
    {/if}

    <div class="graph-grid" class:list-only={mode === 'List'}>
      {#if mode !== 'List'}
        <section class="graph-visual" aria-label="Graph visual overview">
          {#if capStatus}
            <p class="cap-status">{capStatus}</p>
          {/if}
          {#if mode === 'Cluster' && clusterLabels.length}
            <p class="cluster-labels">Clusters: {clusterLabels.join(' · ')}</p>
          {/if}
          <svg viewBox="0 0 {W} {H}" role="img" aria-label="{mode} graph overview">
            {#each renderedEdges as edge (edge.id)}
              <line
                data-testid="graph-edge"
                class="graph-edge edge-{typeClass(edge.type)}"
                x1={edge.x1}
                y1={edge.y1}
                x2={edge.x2}
                y2={edge.y2}
              />
            {/each}
            {#each visibleNodes as node (node.id)}
              <g
                data-testid="graph-node"
                class="graph-node node-{typeClass(node.type)}"
                role={node.type === 'note' ? 'button' : 'img'}
                tabindex={node.type === 'note' ? 0 : undefined}
                aria-label={node.type === 'note' ? `Open note ${node.label}` : `${node.type} ${node.label}`}
                onclick={() => openNode(node)}
                onkeydown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    openNode(node);
                  }
                }}
              >
                <circle cx={node.x} cy={node.y} r={nodeRadius(node)} />
                <text x={node.x + 10} y={node.y - 8}>{node.label}</text>
              </g>
            {/each}
          </svg>
        </section>
      {/if}

      <section class="graph-list" aria-label="Graph list">
        <table aria-label="Graph nodes">
          <thead>
            <tr>
              <th>Node</th>
              <th>Type</th>
              <th>Degree</th>
              <th>Cluster</th>
              <th>Tier</th>
            </tr>
          </thead>
          <tbody>
            {#each listNodes as node (node.id)}
              <tr data-testid="graph-row">
                <td>
                  {#if node.type === 'note'}
                    <button
                      type="button"
                      class="node-link"
                      aria-label="Open note {node.label}"
                      onclick={() => openNode(node)}
                    >
                      {node.label}
                    </button>
                  {:else}
                    <span>{node.label}</span>
                  {/if}
                  <small>{node.id}</small>
                </td>
                <td>{node.type}</td>
                <td>{node.degree}</td>
                <td>{node.community || '—'}</td>
                <td>{node.tier || '—'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    </div>
  {/if}
</main>

<style>
  .graph-page {
    width: min(1180px, calc(100vw - 64px));
    margin: 0 auto;
    padding: var(--space-6, 32px) 0 var(--space-8, 64px);
  }

  .graph-header {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: var(--space-5, 24px);
    margin-bottom: var(--space-5, 24px);
  }

  .eyebrow,
  .graph-summary,
  .mode-switcher,
  .graph-toolbar,
  .status-msg,
  .empty-state,
  .cap-status,
  .cluster-labels,
  table {
    font-family: var(--font-mono);
  }

  .eyebrow {
    margin: 0 0 var(--space-2, 8px);
    color: var(--text-faint);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.14em;
  }

  .graph-summary {
    margin: 0;
    color: var(--text-muted);
  }

  .mode-switcher,
  .graph-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2, 8px);
  }

  .mode-switcher button,
  .node-link,
  select {
    font: inherit;
  }

  .mode-switcher button {
    min-height: 34px;
    color: var(--text-muted);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm, 2px);
    padding: 0 var(--space-3, 12px);
    cursor: pointer;
  }

  .mode-switcher button.active {
    color: var(--text);
    border-color: var(--accent);
    background: var(--accent-bg);
  }

  .graph-toolbar {
    align-items: center;
    justify-content: space-between;
    padding: var(--space-3, 12px) 0;
    border-top: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    margin-bottom: var(--space-4, 16px);
  }

  .graph-toolbar label {
    display: flex;
    align-items: center;
    gap: var(--space-2, 8px);
    color: var(--text-faint);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  select {
    min-height: 32px;
    color: var(--text);
    background: var(--surface-raised);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm, 2px);
  }

  .mode-marker {
    color: var(--text-muted);
  }

  .graph-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.25fr) minmax(340px, 0.75fr);
    gap: var(--space-4, 16px);
  }

  .graph-grid.list-only {
    grid-template-columns: 1fr;
  }

  .graph-visual,
  .graph-list,
  .empty-state {
    background: var(--surface);
    border: 1px solid var(--border);
    border-top-color: var(--accent);
  }

  .graph-visual {
    min-width: 0;
    padding: var(--space-3, 12px);
    overflow: auto;
  }

  svg {
    display: block;
    min-width: 640px;
    width: 100%;
    height: auto;
  }

  .graph-edge {
    stroke: var(--border);
    stroke-width: 1.2;
  }

  .edge-semantic_similar {
    stroke: var(--signal-cyan);
    stroke-dasharray: 4 4;
  }

  .graph-node circle {
    fill: var(--surface-raised);
    stroke: var(--text-muted);
    stroke-width: 1.4;
  }

  .graph-node.node-note circle {
    stroke: var(--accent);
  }

  .graph-node.node-tag circle {
    stroke: var(--signal-cyan);
  }

  .graph-node text {
    fill: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 11px;
    paint-order: stroke;
    stroke: var(--surface);
    stroke-width: 3px;
  }

  .graph-node[role='button'] {
    cursor: pointer;
  }

  .graph-node[role='button']:hover circle,
  .graph-node[role='button']:focus circle {
    fill: var(--accent-bg);
  }

  .cap-status,
  .cluster-labels {
    margin: 0 0 var(--space-2, 8px);
    color: var(--text-muted);
    font-size: var(--type-chrome-size, 13px);
  }

  .graph-list {
    min-width: 0;
    overflow: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--type-chrome-size, 13px);
  }

  th,
  td {
    padding: var(--space-2, 8px) var(--space-3, 12px);
    border-bottom: 1px solid var(--border);
    text-align: left;
    vertical-align: top;
  }

  th {
    color: var(--text-faint);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    font-weight: 600;
  }

  td {
    color: var(--text-muted);
  }

  td:first-child {
    color: var(--text);
  }

  small {
    display: block;
    margin-top: 2px;
    color: var(--text-faint);
  }

  .node-link {
    color: var(--text);
    background: transparent;
    border: 0;
    padding: 0;
    cursor: pointer;
    text-align: left;
  }

  .node-link:hover,
  .node-link:focus-visible {
    color: var(--accent);
  }

  .status-msg {
    color: var(--text-muted);
  }

  .status-msg.error {
    color: var(--signal-danger);
  }

  .status-msg.faint {
    color: var(--text-faint);
  }

  .empty-state {
    padding: var(--space-5, 24px);
    color: var(--text-muted);
  }

  .empty-title {
    margin: 0 0 var(--space-2, 8px);
    color: var(--text);
    font-size: var(--type-body-size, 15px);
  }

  code {
    color: var(--text);
    background: var(--code-bg);
    padding: 1px 4px;
  }

  @media (max-width: 900px) {
    .graph-page {
      width: min(100%, calc(100vw - 32px));
    }

    .graph-header {
      align-items: stretch;
      flex-direction: column;
    }

    .graph-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
