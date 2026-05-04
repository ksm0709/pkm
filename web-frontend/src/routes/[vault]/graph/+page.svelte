<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { apiClient } from '$lib/api/client.js';
  import { graphFocusState } from '$lib/graph/focus.js';
  import { classifyGraphGesture } from '$lib/graph/gestures.js';
  import { labelBudget } from '$lib/graph/labels.js';
  import {
    semanticEdgeDistance,
    settleGraphLayout,
    type PositionedGraphNode
  } from '$lib/graph/layout.js';
  import {
    normalizeGraph,
    type NormalizedGraph,
    type NormalizedGraphEdge,
    type NormalizedGraphNode
  } from '$lib/graph/normalize.js';

  type GraphTestWindow = Window &
    typeof globalThis & {
      __pkmGraphTest?: {
        settle: () => Promise<void> | void;
      };
    };

  type RenderedEdge = NormalizedGraphEdge & {
    x1: number;
    y1: number;
    x2: number;
    y2: number;
    forceDistance: number;
  };

  type PreviewState = {
    node: NormalizedGraphNode;
    title: string;
    body: string;
    loading: boolean;
    error: string;
  };

  const GRAPH_WIDTH = 1000;
  const GRAPH_HEIGHT = 640;
  const INTERACTIVE_NODE_CAP = 300;
  const LONG_PRESS_MS = 500;
  const DEFAULT_ATTRACTION = 1;
  const DEFAULT_REPULSION = 1.6;
  const DEFAULT_ZOOM = 1;

  let vaultName = $derived($page.params.vault ?? '');
  let loading = $state(true);
  let error = $state('');
  let missingGraph = $state(false);
  let rawGraph = $state<unknown>(null);
  let loadToken = 0;
  let focusedId = $state<string | null>(null);
  let hoveredId = $state<string | null>(null);
  let preview = $state<PreviewState | null>(null);
  let pointerStart = $state<{ id: string; startedAt: number; button: number } | null>(null);
  let attractionStrength = $state(DEFAULT_ATTRACTION);
  let repulsionStrength = $state(DEFAULT_REPULSION);
  let zoomLevel = $state(DEFAULT_ZOOM);

  const graph = $derived(normalizeGraph(rawGraph));
  const interactiveGraph = $derived(selectInteractiveGraph(graph));
  const positionedNodes = $derived(
    settleGraphLayout(interactiveGraph, {
      width: GRAPH_WIDTH,
      height: GRAPH_HEIGHT,
      ticks: layoutTickCount(interactiveGraph.nodes.length),
      seed: 'pkm-reactive-graph',
      attraction: attractionStrength,
      repulsion: repulsionStrength,
      collisionPadding: 8 + repulsionStrength * 4
    })
  );
  const renderedEdges = $derived(renderEdges(interactiveGraph.edges, positionedNodes));
  const focusStates = $derived(graphFocusState(interactiveGraph, focusedId, 1));
  const visibleLabels = $derived(
    labelBudget(positionedNodes, {
      focusedId,
      hoveredId,
      selectedId: preview?.node.id ?? null,
      maxLabels: 24
    })
  );
  const focusedNode = $derived(
    focusedId ? interactiveGraph.nodes.find((node) => node.id === focusedId) ?? null : null
  );
  const capStatus = $derived(
    graph.nodes.length > INTERACTIVE_NODE_CAP
      ? `Rendering first ${INTERACTIVE_NODE_CAP} of ${graph.nodes.length} nodes by graph importance.`
      : ''
  );
  const graphTransformStyle = $derived(`transform: scale(${zoomLevel});`);

  $effect(() => {
    if (!vaultName) return;
    void loadGraph(vaultName);
  });

  $effect(() => {
    if (typeof window === 'undefined') return;
    const graphWindow = window as GraphTestWindow;
    graphWindow.__pkmGraphTest = {
      settle: async () => {
        const deadline = Date.now() + 4000;
        while (loading && Date.now() < deadline) {
          await new Promise((resolve) => window.setTimeout(resolve, 25));
        }
        await nextFrame();
        await nextFrame();
      }
    };

    return () => {
      delete graphWindow.__pkmGraphTest;
    };
  });

  async function loadGraph(vault: string) {
    const token = ++loadToken;
    loading = true;
    error = '';
    missingGraph = false;
    rawGraph = null;
    focusedId = null;
    hoveredId = null;
    preview = null;

    try {
      const response = await apiClient(`/api/v1/vault/${encodeURIComponent(vault)}/graph`, {
        method: 'GET'
      });
      if (token !== loadToken) return;
      if (response.status === 404) {
        missingGraph = true;
        return;
      }
      if (!response.ok) throw new Error(`GET graph -> ${response.status}`);
      rawGraph = await response.json();
    } catch (e) {
      if (token !== loadToken) return;
      error = e instanceof Error ? e.message : 'Failed to load graph.';
    } finally {
      if (token === loadToken) loading = false;
    }
  }

  function selectInteractiveGraph(source: NormalizedGraph): NormalizedGraph {
    if (source.nodes.length <= INTERACTIVE_NODE_CAP) return source;

    const nodeIds = new Set(
      [...source.nodes]
        .sort(compareGraphImportance)
        .slice(0, INTERACTIVE_NODE_CAP)
        .map((node) => node.id)
    );

    return {
      ...source,
      nodes: source.nodes.filter((node) => nodeIds.has(node.id)),
      edges: source.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    };
  }

  function renderEdges(
    edges: NormalizedGraphEdge[],
    nodes: PositionedGraphNode[]
  ): RenderedEdge[] {
    const byId = new Map(nodes.map((node) => [node.id, node]));

    return edges.flatMap((edge) => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      if (!source || !target) return [];

      return [
        {
          ...edge,
          x1: source.x,
          y1: source.y,
          x2: target.x,
          y2: target.y,
          forceDistance: semanticEdgeDistance(edge)
        }
      ];
    });
  }

  function layoutTickCount(nodeCount: number) {
    if (nodeCount >= 240) return 26;
    if (nodeCount >= 90) return 48;
    return 190;
  }

  function focusNode(node: NormalizedGraphNode) {
    focusedId = node.id;
    preview = null;
  }

  async function openPreview(node: NormalizedGraphNode) {
    if (node.type !== 'note') {
      focusNode(node);
      return;
    }

    focusedId = node.id;
    preview = {
      node,
      title: node.label,
      body: '',
      loading: true,
      error: ''
    };

    try {
      const response = await apiClient(
        `/api/v1/vault/${encodeURIComponent(vaultName)}/notes/${encodeURIComponent(node.id)}`,
        { method: 'GET' }
      );
      if (!response.ok) throw new Error(`preview -> ${response.status}`);
      const payload = await response.json();
      if (!preview || preview.node.id !== node.id) return;

      preview = {
        node,
        title: stringValue(payload.title) || stringValue(payload.note_id) || node.label,
        body: stringValue(payload.body) || stringValue(payload.content) || '',
        loading: false,
        error: ''
      };
    } catch (e) {
      if (!preview || preview.node.id !== node.id) return;
      preview = {
        ...preview,
        loading: false,
        error: e instanceof Error ? e.message : 'preview failed'
      };
    }
  }

  function openNote(node: NormalizedGraphNode) {
    void goto(`/${encodeURIComponent(vaultName)}/notes/${encodeURIComponent(node.id)}`);
  }

  function handlePointerDown(node: NormalizedGraphNode, event: PointerEvent) {
    pointerStart = { id: node.id, startedAt: Date.now(), button: event.button };
  }

  async function handleNodeClick(node: NormalizedGraphNode, event: MouseEvent) {
    const started = pointerStart?.id === node.id ? pointerStart : null;
    pointerStart = null;
    const action = classifyGraphGesture({
      nodeType: node.type,
      durationMs: started ? Date.now() - started.startedAt : 0,
      metaKey: event.metaKey,
      ctrlKey: event.ctrlKey,
      button: started?.button ?? event.button,
      longPressMs: LONG_PRESS_MS
    });

    if (action === 'preview') await openPreview(node);
    else if (action === 'focus') focusNode(node);
  }

  function handleKeydown(node: NormalizedGraphNode, event: KeyboardEvent) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    focusNode(node);
  }

  function setAttraction(event: Event) {
    attractionStrength = numberInputValue(event, DEFAULT_ATTRACTION);
  }

  function setRepulsion(event: Event) {
    repulsionStrength = numberInputValue(event, DEFAULT_REPULSION);
  }

  function setZoom(event: Event) {
    zoomLevel = numberInputValue(event, DEFAULT_ZOOM);
  }

  function zoomBy(delta: number) {
    zoomLevel = roundControl(clampControl(zoomLevel + delta, 0.6, 1.8));
  }

  function resetGraphControls() {
    attractionStrength = DEFAULT_ATTRACTION;
    repulsionStrength = DEFAULT_REPULSION;
    zoomLevel = DEFAULT_ZOOM;
  }

  function nodeColor(node: NormalizedGraphNode) {
    if (node.hub) return '#2563eb';
    if (node.type === 'tag') return '#0f766e';
    if (node.type === 'note_or_unresolved') return '#9a3412';
    return '#374151';
  }

  function nodeStroke(node: NormalizedGraphNode) {
    if (node.hub) return '#1d4ed8';
    if (node.type === 'tag') return '#115e59';
    if (node.type === 'note_or_unresolved') return '#7c2d12';
    return '#111827';
  }

  function nodeStyle(node: PositionedGraphNode, nodeIndex: number) {
    const size = Math.max(22, node.radius * 2);
    return [
      `left: ${positionPercent(node.x, GRAPH_WIDTH)}%`,
      `top: ${positionPercent(node.y, GRAPH_HEIGHT)}%`,
      `width: ${size}px`,
      `height: ${size}px`,
      `background: ${nodeColor(node)}`,
      `border-color: ${nodeStroke(node)}`,
      `z-index: ${1000 - nodeIndex}`
    ].join('; ');
  }

  function labelStyle(node: PositionedGraphNode) {
    return [
      `left: calc(${positionPercent(node.x, GRAPH_WIDTH)}% + ${node.radius + 6}px)`,
      `top: ${positionPercent(node.y, GRAPH_HEIGHT)}%`
    ].join('; ');
  }

  function typeClass(value: string) {
    return value.replace(/[^a-z0-9_-]/gi, '-').toLowerCase();
  }

  function positionPercent(value: number, size: number) {
    return (value / size) * 100;
  }

  function numberInputValue(event: Event, fallback: number) {
    const target = event.currentTarget;
    if (!(target instanceof HTMLInputElement)) return fallback;
    const parsed = Number(target.value);
    return Number.isFinite(parsed) ? roundControl(parsed) : fallback;
  }

  function clampControl(value: number, min: number, max: number) {
    return Math.max(min, Math.min(max, value));
  }

  function roundControl(value: number) {
    return Math.round(value * 10) / 10;
  }

  function formatNumber(value: number) {
    return Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
  }

  function stringValue(value: unknown) {
    return typeof value === 'string' ? value : '';
  }

  function compareGraphImportance(a: NormalizedGraphNode, b: NormalizedGraphNode) {
    return (
      Number(b.hub) - Number(a.hub) ||
      b.importance - a.importance ||
      b.degree - a.degree ||
      b.radius - a.radius ||
      a.label.localeCompare(b.label) ||
      a.id.localeCompare(b.id)
    );
  }

  function nextFrame() {
    return new Promise((resolve) => window.requestAnimationFrame(resolve));
  }
</script>

<svelte:head>
  <title>Graph - {vaultName} - pkm</title>
</svelte:head>

<main class="graph-page">
  {#if loading}
    <section class="graph-layout" data-testid="graph-layout" data-preview-open="false">
      <div class="graph-stage">
        <div class="graph-topline">
          <p class="graph-summary" data-testid="graph-summary">Loading graph...</p>
          <p class="graph-focus-status" data-testid="graph-focus-status">Focus: full graph</p>
        </div>
        <div class="force-surface" data-testid="graph-force-surface" role="application" aria-label="Vault graph">
          <p class="status-msg">Loading graph...</p>
        </div>
      </div>
    </section>
  {:else if missingGraph}
    <section class="empty-state" aria-label="Missing graph index">
      <p class="empty-title">Graph index not found.</p>
      <p>Run <code>pkm index</code> for this vault, then reopen Graph.</p>
    </section>
  {:else if error}
    <p class="status-msg error">{error}</p>
  {:else if graph.nodes.length === 0}
    <section class="empty-state" aria-label="Empty graph">
      <p class="empty-title">Graph is empty.</p>
      <p>Run <code>pkm index</code> after adding notes or links to populate the graph.</p>
    </section>
  {:else}
    <section
      class="graph-layout"
      class:preview-open={Boolean(preview)}
      data-testid="graph-layout"
      data-preview-open={preview ? 'true' : 'false'}
    >
      <div class="graph-stage">
        <div class="graph-topline">
          <p class="graph-summary" data-testid="graph-summary">
            <strong>{graph.nodes.length}</strong> nodes · <strong>{graph.edges.length}</strong> edges
          </p>
          <p class="graph-focus-status" data-testid="graph-focus-status">
            {#if focusedNode}
              Focus: {focusedNode.label}
            {:else}
              Focus: full graph
            {/if}
          </p>
        </div>

        {#if capStatus}
          <p class="cap-status" data-testid="graph-cap-status">{capStatus}</p>
        {/if}

        <div class="graph-controls" data-testid="graph-controls" aria-label="Graph force controls">
          <label>
            <span>Attraction <output aria-hidden="true">{formatNumber(attractionStrength)}</output></span>
            <input
              aria-label="Attraction"
              type="range"
              min="0.4"
              max="2.2"
              step="0.1"
              value={attractionStrength}
              oninput={setAttraction}
            />
          </label>
          <label>
            <span>Repulsion <output aria-hidden="true">{formatNumber(repulsionStrength)}</output></span>
            <input
              aria-label="Repulsion"
              type="range"
              min="0.4"
              max="3"
              step="0.1"
              value={repulsionStrength}
              oninput={setRepulsion}
            />
          </label>
          <label>
            <span>Zoom <output aria-hidden="true">{formatNumber(zoomLevel)}</output></span>
            <input
              aria-label="Zoom"
              type="range"
              min="0.6"
              max="1.8"
              step="0.1"
              value={zoomLevel}
              oninput={setZoom}
            />
          </label>
          <div class="zoom-buttons" aria-label="Zoom buttons">
            <button type="button" aria-label="Zoom out" onclick={() => zoomBy(-0.1)}>−</button>
            <button type="button" aria-label="Zoom in" onclick={() => zoomBy(0.1)}>+</button>
            <button type="button" aria-label="Reset graph controls" onclick={resetGraphControls}>Reset</button>
          </div>
        </div>

        <div
          class="force-surface"
          data-testid="graph-force-surface"
          data-attraction={formatNumber(attractionStrength)}
          data-repulsion={formatNumber(repulsionStrength)}
          data-zoom={formatNumber(zoomLevel)}
          role="application"
          aria-label="Vault graph"
        >
          <svg class="edge-surface" style={graphTransformStyle} viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`} aria-hidden="true">
            <g class="edges">
              {#each renderedEdges as edge (edge.id)}
                <line
                  data-testid="graph-edge"
                  data-source={edge.source}
                  data-target={edge.target}
                  data-edge-type={edge.type}
                  data-confidence={formatNumber(edge.confidence)}
                  data-weight={formatNumber(edge.weight)}
                  data-force-distance={formatNumber(edge.forceDistance)}
                  class={`graph-edge edge-${typeClass(edge.type)}`}
                  x1={edge.x1}
                  y1={edge.y1}
                  x2={edge.x2}
                  y2={edge.y2}
                />
              {/each}
            </g>
          </svg>

          <div class="node-layer" style={graphTransformStyle}>
            {#each positionedNodes as node, nodeIndex (node.id)}
              {@const state = focusStates.get(node.id) ?? 'normal'}
              <button
                type="button"
                aria-label={`${node.label} graph node`}
                data-testid="graph-node"
                data-node-id={node.id}
                data-node-type={node.type}
                data-hub={node.hub ? 'true' : 'false'}
                data-size={formatNumber(node.radius)}
                data-degree={node.degree}
                data-focus-state={state}
                data-position={`${formatNumber(node.x)},${formatNumber(node.y)}`}
                class={`graph-node node-${typeClass(node.type)} state-${state} ${node.hub ? 'node-hub' : ''}`}
                style={nodeStyle(node, nodeIndex)}
                onpointerdown={(event) => handlePointerDown(node, event)}
                onclick={(event) => void handleNodeClick(node, event)}
                onkeydown={(event) => handleKeydown(node, event)}
                onmouseenter={() => {
                  hoveredId = node.id;
                }}
                onmouseleave={() => {
                  if (hoveredId === node.id) hoveredId = null;
                }}
              ></button>
              {#if visibleLabels.has(node.id)}
                <span
                  class={`graph-label ${node.hub ? 'hub-label' : ''}`}
                  data-testid="graph-label"
                  data-node-id={node.id}
                  style={labelStyle(node)}
                >
                  {node.label}
                </span>
              {/if}
            {/each}
          </div>
        </div>

        <div class="legend" aria-label="Graph legend">
          <span><i class="note"></i>Note</span>
          <span><i class="tag"></i>Tag</span>
          <span><i class="hub"></i>Hub</span>
          <span><i class="unresolved"></i>Unresolved</span>
        </div>
      </div>

      {#if preview}
        <aside class="preview-sheet" data-testid="graph-preview-sheet" aria-label="Graph note preview">
          <div class="preview-head">
            <div>
              <p class="preview-kicker">Preview</p>
              <h2>{preview.title}</h2>
            </div>
            <button
              type="button"
              class="open-note"
              aria-label={`Open note ${preview.node.label}`}
              onclick={() => openNote(preview.node)}
            >
              ⤢
            </button>
          </div>

          {#if preview.loading}
            <p class="preview-status">Loading preview...</p>
          {:else if preview.error}
            <p class="preview-status error" data-testid="graph-preview-error">{preview.error}</p>
          {:else}
            <pre class="preview-body">{preview.body}</pre>
          {/if}
        </aside>
      {/if}
    </section>
  {/if}
</main>

<style>
  .graph-page {
    min-height: 100%;
    padding: 0;
    color: var(--text);
    background: var(--bg);
  }

  .status-msg,
  .empty-state {
    margin: 24px;
    color: var(--text-muted);
  }

  .status-msg.error,
  .preview-status.error {
    color: var(--signal-danger);
  }

  .empty-title {
    margin: 0 0 8px;
    color: var(--text);
    font-size: 16px;
    font-weight: 700;
  }

  .graph-layout {
    display: grid;
    min-height: calc(100vh - 58px);
    grid-template-columns: minmax(0, 1fr);
    background: var(--bg);
  }

  .graph-layout.preview-open {
    grid-template-columns: minmax(0, 1fr) minmax(340px, 42vw);
  }

  .graph-stage {
    display: flex;
    min-width: 0;
    flex-direction: column;
    padding: 14px 18px 16px;
  }

  .graph-topline {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 8px;
  }

  .graph-summary,
  .graph-focus-status,
  .cap-status {
    margin: 0;
    color: var(--text-muted);
    font-size: 13px;
    line-height: 1.45;
  }

  .graph-summary strong {
    color: var(--text);
  }

  .cap-status {
    margin-bottom: 8px;
  }

  .graph-controls {
    display: grid;
    grid-template-columns: repeat(3, minmax(140px, 1fr)) auto;
    align-items: end;
    gap: 10px;
    margin-bottom: 10px;
    padding: 10px 0;
    border-top: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
  }

  .graph-controls label {
    display: grid;
    gap: 5px;
    min-width: 0;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    line-height: var(--type-chrome-sm-lh, 1.2);
    text-transform: uppercase;
  }

  .graph-controls label span {
    display: flex;
    justify-content: space-between;
    gap: 8px;
  }

  .graph-controls output {
    color: var(--text);
  }

  .graph-controls input[type='range'] {
    width: 100%;
    accent-color: var(--accent);
  }

  .zoom-buttons {
    display: flex;
    gap: 6px;
  }

  .zoom-buttons button {
    min-width: 34px;
    min-height: 30px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm, 2px);
    color: var(--text);
    background: var(--surface-raised);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
  }

  .force-surface {
    position: relative;
    min-height: 0;
    flex: 1;
    width: 100%;
    border: 1px solid var(--border);
    background: var(--surface);
    overflow: hidden;
  }

  .edge-surface {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    transform-origin: 50% 50%;
  }

  .graph-edge {
    stroke: var(--border);
    stroke-linecap: round;
    stroke-width: 1.1;
  }

  .edge-semantic_similar,
  .edge-semantic_similarity {
    stroke: #94a3b8;
    stroke-dasharray: 5 5;
    stroke-width: 1.4;
  }

  .edge-has_tag,
  .edge-tagged_by {
    stroke: #99f6e4;
  }

  .graph-node {
    position: absolute;
    z-index: 2;
    display: block;
    padding: 0;
    border: 1.5px solid;
    border-radius: 999px;
    cursor: pointer;
    transform: translate(-50%, -50%);
    outline: none;
    transition:
      opacity 140ms ease,
      border-width 140ms ease,
      box-shadow 140ms ease;
  }

  .graph-node:focus-visible,
  .graph-node.state-focused {
    border-width: 3px;
    box-shadow: 0 0 0 3px rgb(37 99 235 / 0.16);
  }

  .graph-node.state-muted {
    opacity: 0.2;
  }

  .graph-node.state-neighbor {
    opacity: 0.74;
  }

  .node-layer {
    position: absolute;
    inset: 0;
    transform-origin: 50% 50%;
  }

  .graph-label {
    position: absolute;
    z-index: 1200;
    max-width: min(220px, 28vw);
    overflow: hidden;
    color: var(--text);
    font-size: 13px;
    pointer-events: none;
    text-overflow: ellipsis;
    text-shadow:
      0 1px 0 var(--surface),
      1px 0 0 var(--surface),
      -1px 0 0 var(--surface),
      0 -1px 0 var(--surface);
    transform: translateY(-50%);
    white-space: nowrap;
  }

  .hub-label {
    font-weight: 700;
  }

  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-top: 10px;
    color: var(--text-muted);
    font-size: 12px;
  }

  .legend span {
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }

  .legend i {
    display: inline-block;
    width: 9px;
    height: 9px;
    border-radius: 999px;
    background: #374151;
  }

  .legend .tag {
    background: #0f766e;
  }

  .legend .hub {
    background: #2563eb;
  }

  .legend .unresolved {
    background: #9a3412;
  }

  .preview-sheet {
    display: flex;
    min-height: 0;
    flex-direction: column;
    border-left: 1px solid var(--border);
    background: var(--surface);
    box-shadow: -10px 0 24px rgb(0 0 0 / 0.18);
  }

  .preview-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    padding: 18px 18px 12px;
    border-bottom: 1px solid var(--border);
  }

  .preview-kicker {
    margin: 0 0 4px;
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .preview-head h2 {
    margin: 0;
    color: var(--text);
    font-size: 18px;
    line-height: 1.25;
  }

  .open-note {
    width: 34px;
    height: 34px;
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    background: var(--surface-raised);
    cursor: pointer;
    font-size: 18px;
    line-height: 1;
  }

  .preview-status {
    margin: 18px;
    color: var(--text-muted);
  }

  .preview-body {
    flex: 1;
    margin: 0;
    overflow: auto;
    padding: 18px;
    color: var(--text-muted);
    font: inherit;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;
  }

  @media (max-width: 860px) {
    .graph-layout.preview-open {
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: minmax(300px, 50vh) minmax(280px, 1fr);
    }

    .graph-stage {
      padding: 10px;
    }

    .graph-topline {
      align-items: flex-start;
      flex-direction: column;
      gap: 4px;
    }

    .graph-controls {
      grid-template-columns: 1fr;
      align-items: stretch;
      gap: 8px;
    }

    .zoom-buttons {
      justify-content: stretch;
    }

    .zoom-buttons button {
      flex: 1;
    }

    .force-surface {
      min-height: 360px;
    }

    .preview-sheet {
      border-top: 1px solid var(--border);
      border-left: 0;
      box-shadow: 0 -10px 22px rgb(0 0 0 / 0.18);
    }
  }
</style>
