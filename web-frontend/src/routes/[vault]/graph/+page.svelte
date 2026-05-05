<script lang="ts">
  import { untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { apiClient } from '$lib/api/client.js';
  import { graphFocusState } from '$lib/graph/focus.js';
  import { classifyGraphGesture } from '$lib/graph/gestures.js';
  import { hitTestNode } from '$lib/graph/hit-test.js';
  import {
    createGraphSimulation,
    type GraphSimulationController,
    type GraphSimulationLink,
    type GraphSimulationNode
  } from '$lib/graph/simulation.js';
  import {
    fitToBounds,
    panTransform,
    screenToWorld,
    wheelZoomTransform,
    zoomAt,
    type GraphTransform
  } from '$lib/graph/viewport.js';
  import { normalizeGraph, type NormalizedGraph, type NormalizedGraphNode } from '$lib/graph/normalize.js';

  type PreviewState = {
    node: NormalizedGraphNode;
    title: string;
    body: string;
    loading: boolean;
    error: string;
  };

  type GraphTestApi = {
    settle: (ticks?: number) => Promise<void>;
    getNode: (id: string) => ReturnType<typeof serializeNode>;
    getEdge: (source: string, target: string, type?: string) => ReturnType<typeof serializeEdge>;
    getTransform: () => GraphTransform;
    getFocusState: (id: string) => string | null;
    hitTest: (screenX: number, screenY: number) => { id: string } | null;
    dragNode: (id: string, dx: number, dy: number) => Promise<void>;
    getRenderedCounts: () => { nodes: number; edges: number; labels: number };
    getForceOptions: () => { repulsion: number; linkDistance: number };
    getSimulationState: () => { generation: number; alpha: number; paused: boolean };
    getWorldState: () => ReturnType<typeof graphWorldState>;
  };

  type GraphWindow = Window &
    typeof globalThis & {
      __pkmGraphTest?: GraphTestApi;
    };

  const GRAPH_FALLBACK_WIDTH = 1200;
  const GRAPH_FALLBACK_HEIGHT = 780;
  const GRAPH_WORLD_VIEWPORT_SCALE = 3.2;
  const GRAPH_WORLD_NODE_SPACING_X = 340;
  const GRAPH_WORLD_NODE_SPACING_Y = 230;
  const INTERACTIVE_NODE_CAP = 300;
  const LONG_PRESS_MS = 500;

  let vaultName = $derived($page.params.vault ?? '');
  let loading = $state(true);
  let error = $state('');
  let missingGraph = $state(false);
  let rawGraph = $state<unknown>(null);
  let focusedId = $state<string | null>(null);
  let hoveredId = $state<string | null>(null);
  let selectedId = $state<string | null>(null);
  let preview = $state<PreviewState | null>(null);
  let searchQuery = $state('');
  let paused = $state(false);
  let transform = $state<GraphTransform>({ x: 0, y: 0, k: 1 });
  let renderVersion = $state(0);
  let repulsion = $state(-420);
  let linkDistance = $state(92);
  let graphWorld = { width: GRAPH_FALLBACK_WIDTH, height: GRAPH_FALLBACK_HEIGHT };

  let loadToken = 0;
  let canvas = $state<HTMLCanvasElement | null>(null);
  let simulation: GraphSimulationController | null = null;
  let simulationGeneration = 0;
  let raf = 0;
  let pointer:
    | { mode: 'node'; nodeId: string; x: number; y: number; startedAt: number; moved: boolean }
    | { mode: 'pan'; x: number; y: number; startedAt: number; moved: boolean }
    | null = null;

  const graph = $derived(normalizeGraph(rawGraph));
  const interactiveGraph = $derived(selectInteractiveGraph(graph));
  const focusStates = $derived(graphFocusState(interactiveGraph, focusedId, 1));
  const focusedNode = $derived(
    focusedId ? interactiveGraph.nodes.find((node) => node.id === focusedId) ?? null : null
  );
  const searchResults = $derived(searchGraphNodes(interactiveGraph.nodes, searchQuery));
  const a11yStatus = $derived(accessibilityStatus());
  const capStatus = $derived(
    graph.nodes.length > INTERACTIVE_NODE_CAP
      ? `Rendering first ${INTERACTIVE_NODE_CAP} of ${graph.nodes.length} nodes by graph importance.`
      : ''
  );

  $effect(() => {
    if (!vaultName) return;
    void loadGraph(vaultName);
  });

  $effect(() => {
    if (!canvas || loading || error || missingGraph || interactiveGraph.nodes.length === 0) return;

    simulation?.dispose();
    cancelAnimationFrame(raf);
    const size = canvasSize();
    graphWorld = graphWorldSize(size, interactiveGraph.nodes.length);
    const initialForce = untrack(() => ({ repulsion, linkDistance }));
    simulationGeneration += 1;
    simulation = createGraphSimulation(interactiveGraph, {
      width: graphWorld.width,
      height: graphWorld.height,
      seed: `pkm:${vaultName}`,
      chargeStrength: initialForce.repulsion,
      linkDistance: initialForce.linkDistance,
      autoStart: true,
      onTick: scheduleDraw
    });
    transform = fitToBounds({ minX: 0, minY: 0, maxX: graphWorld.width, maxY: graphWorld.height }, size, 0);
    paused = false;
    scheduleDraw();
    installTestApi();

    return () => {
      simulation?.dispose();
      simulation = null;
      cancelAnimationFrame(raf);
      uninstallTestApi();
    };
  });

  $effect(() => {
    renderVersion;
    focusedId;
    hoveredId;
    selectedId;
    preview;
    scheduleDraw();
  });

  async function loadGraph(vault: string) {
    const token = ++loadToken;
    loading = true;
    error = '';
    missingGraph = false;
    rawGraph = null;
    focusedId = null;
    hoveredId = null;
    selectedId = null;
    preview = null;
    searchQuery = '';

    try {
      const response = await apiClient(`/api/v1/vault/${encodeURIComponent(vault)}/graph`, { method: 'GET' });
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

  function scheduleDraw() {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      drawGraph();
    });
  }

  function drawGraph() {
    if (!canvas || !simulation) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(1, rect.width);
    const height = Math.max(1, rect.height);
    if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
    }

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const palette = graphPalette();
    const states = focusStates;
    const nodes = simulation.nodes();
    const nodeById = new Map(nodes.map((node) => [node.id, node]));
    const labels = visibleLabelIds(nodes);

    ctx.lineCap = 'round';
    for (const edge of simulation.links()) {
      if (!edge.visible) continue;
      const source = linkNode(edge.source, nodeById);
      const target = linkNode(edge.target, nodeById);
      if (!source || !target) continue;
      const sourceState = states.get(source.id) ?? 'normal';
      const targetState = states.get(target.id) ?? 'normal';
      const muted = sourceState === 'muted' && targetState === 'muted';
      const a = worldToCanvas(source);
      const b = worldToCanvas(target);
      ctx.globalAlpha = muted ? 0.08 : edge.type.includes('semantic') ? 0.28 : 0.42;
      ctx.strokeStyle = edge.type.includes('semantic') ? palette.semanticEdge : palette.edge;
      ctx.lineWidth = edge.type.includes('semantic') ? 1.1 : 0.9;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }

    for (const node of nodes) {
      const state = states.get(node.id) ?? 'normal';
      const pos = worldToCanvas(node);
      ctx.globalAlpha = state === 'muted' ? 0.18 : 1;
      ctx.fillStyle = nodeColor(node, palette);
      ctx.strokeStyle = nodeStroke(node, palette);
      ctx.lineWidth = node.id === focusedId ? 3 : node.hub ? 2.5 : 1.4;
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, Math.max(3, node.radius * transform.k), 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      if (node.id === hoveredId || node.id === selectedId || node.id === focusedId) {
        ctx.globalAlpha = 0.28;
        ctx.strokeStyle = palette.accent;
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, Math.max(6, (node.radius + 5) * transform.k), 0, Math.PI * 2);
        ctx.stroke();
      }
    }

    ctx.font = '12px var(--font-mono, monospace)';
    ctx.textBaseline = 'middle';
    for (const node of nodes) {
      if (!labels.has(node.id)) continue;
      const state = states.get(node.id) ?? 'normal';
      const pos = worldToCanvas(node);
      ctx.globalAlpha = state === 'muted' ? 0.22 : 0.9;
      ctx.fillStyle = palette.label;
      ctx.fillText(node.label, pos.x + node.radius * transform.k + 6, pos.y);
    }
    ctx.globalAlpha = 1;
  }

  function worldToCanvas(point: { x: number; y: number }) {
    return {
      x: point.x * transform.k + transform.x,
      y: point.y * transform.k + transform.y
    };
  }

  function visibleLabelIds(nodes: GraphSimulationNode[]) {
    const labels = new Set<string>();
    for (const id of [focusedId, hoveredId, selectedId]) {
      if (id) labels.add(id);
    }
    const candidates = [...nodes]
      .filter((node) => !labels.has(node.id))
      .filter((node) => node.hub || node.degree >= 3 || node.importance >= 0.45)
      .sort(compareGraphImportance);
    for (const node of candidates) {
      if (labels.size >= 40) break;
      labels.add(node.id);
    }
    return labels;
  }

  function handleWheel(event: WheelEvent) {
    event.preventDefault();
    const point = relativePoint(event);
    transform = wheelZoomTransform(transform, point, event.deltaY);
    scheduleDraw();
  }

  function handlePointerDown(event: PointerEvent) {
    if (!canvas || !simulation) return;
    canvas.setPointerCapture(event.pointerId);
    const point = relativePoint(event);
    const node = hitTestNode(simulation.nodes(), point, transform);
    if (node) {
      pointer = { mode: 'node', nodeId: node.id, x: point.x, y: point.y, startedAt: Date.now(), moved: false };
      node.fx = node.x;
      node.fy = node.y;
      selectedId = node.id;
      simulation.reheat(0.25);
    } else {
      pointer = { mode: 'pan', x: point.x, y: point.y, startedAt: Date.now(), moved: false };
    }
  }

  function handlePointerMove(event: PointerEvent) {
    if (!pointer || !simulation) return;
    const point = relativePoint(event);
    const dx = point.x - pointer.x;
    const dy = point.y - pointer.y;
    if (Math.hypot(dx, dy) > 2) pointer.moved = true;

    if (pointer.mode === 'pan') {
      transform = panTransform(transform, dx, dy);
      pointer.x = point.x;
      pointer.y = point.y;
      scheduleDraw();
    } else {
      const node = simulation.nodes().find((entry) => entry.id === pointer?.nodeId);
      if (node) {
        const world = screenToWorld(point, transform);
        node.fx = world.x;
        node.fy = world.y;
        node.x = world.x;
        node.y = world.y;
        simulation.reheat(0.2);
        scheduleDraw();
      }
    }
  }

  async function handlePointerUp(event: PointerEvent) {
    if (!pointer || !simulation) return;
    const ended = pointer;
    const node = ended.mode === 'node' ? simulation.nodes().find((entry) => entry.id === ended.nodeId) : null;
    if (node) {
      node.fx = null;
      node.fy = null;
    }
    pointer = null;

    if (!node || ended.moved) return;
    const action = classifyGraphGesture({
      nodeType: node.type,
      durationMs: Date.now() - ended.startedAt,
      metaKey: event.metaKey,
      ctrlKey: event.ctrlKey,
      button: event.button,
      longPressMs: LONG_PRESS_MS
    });
    if (action === 'preview') await openPreview(node);
    else if (action === 'focus') focusNode(node);
  }

  function handlePointerCancel() {
    if (pointer?.mode === 'node' && simulation) {
      const node = simulation.nodes().find((entry) => entry.id === pointer?.nodeId);
      if (node) {
        node.fx = null;
        node.fy = null;
      }
    }
    pointer = null;
  }

  function relativePoint(event: PointerEvent | WheelEvent | MouseEvent) {
    const rect = canvas?.getBoundingClientRect();
    return {
      x: event.clientX - (rect?.left ?? 0),
      y: event.clientY - (rect?.top ?? 0)
    };
  }

  function focusNode(node: NormalizedGraphNode | GraphSimulationNode) {
    focusedId = node.id;
    selectedId = node.id;
    preview = null;
    renderVersion += 1;
  }

  async function openPreview(node: NormalizedGraphNode | GraphSimulationNode) {
    if (node.type !== 'note') {
      focusNode(node);
      return;
    }
    focusedId = node.id;
    selectedId = node.id;
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
      preview = { ...preview, loading: false, error: e instanceof Error ? e.message : 'preview failed' };
    }
  }

  function openNote(node: NormalizedGraphNode) {
    void goto(`/${encodeURIComponent(vaultName)}/notes/${encodeURIComponent(node.id)}`);
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key !== 'Escape') return;
    if (preview) {
      preview = null;
      return;
    }
    focusedId = null;
    selectedId = null;
    renderVersion += 1;
  }

  function setPaused() {
    if (!simulation) return;
    if (paused) {
      simulation.resume();
      paused = false;
    } else {
      simulation.pause();
      paused = true;
    }
  }

  function updateRepulsion(event: Event) {
    repulsion = Number((event.currentTarget as HTMLInputElement).value);
    simulation?.setForceOptions({ chargeStrength: repulsion });
    scheduleDraw();
  }

  function updateLinkDistance(event: Event) {
    linkDistance = Number((event.currentTarget as HTMLInputElement).value);
    simulation?.setForceOptions({ linkDistance });
    scheduleDraw();
  }

  function zoomBy(delta: number) {
    if (!canvas) return;
    const size = canvasSize();
    transform = zoomAt(transform, { x: size.width / 2, y: size.height / 2 }, transform.k + delta);
    scheduleDraw();
  }

  function resetView() {
    if (!canvas) return;
    transform = fitToBounds({ minX: 0, minY: 0, maxX: graphWorld.width, maxY: graphWorld.height }, canvasSize(), 0);
    scheduleDraw();
  }

  function installTestApi() {
    if (typeof window === 'undefined') return;
    const testHost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    if (!import.meta.env.DEV && import.meta.env.VITE_PKM_GRAPH_TEST_API !== '1' && !testHost) return;
    const graphWindow = window as GraphWindow;
    graphWindow.__pkmGraphTest = {
      settle: async (ticks = 180) => {
        simulation?.settle(ticks);
        drawGraph();
        renderVersion += 1;
      },
      getNode: (id) => serializeNode(simulation?.nodes().find((node) => node.id === id) ?? null),
      getEdge: (source, target, type) => {
        const edge =
          simulation
            ?.links()
            .find(
              (entry) =>
                linkId(entry.source) === source &&
                linkId(entry.target) === target &&
                (!type || entry.type === type)
            ) ?? null;
        return serializeEdge(edge);
      },
      getTransform: () => ({ ...transform }),
      getFocusState: (id) => focusStates.get(id) ?? null,
      hitTest: (screenX, screenY) => {
        if (!simulation) return null;
        const node = hitTestNode(simulation.nodes(), { x: screenX, y: screenY }, transform);
        return node ? { id: node.id } : null;
      },
      dragNode: async (id, dx, dy) => {
        const node = simulation?.nodes().find((entry) => entry.id === id);
        if (!node || !simulation) return;
        node.x += dx;
        node.y += dy;
        node.fx = node.x;
        node.fy = node.y;
        simulation.reheat(0.25);
        simulation.settle(12);
        node.fx = null;
        node.fy = null;
        drawGraph();
        renderVersion += 1;
      },
      getRenderedCounts: () => ({
        nodes: simulation?.nodes().filter((node) => node.visible).length ?? 0,
        edges: simulation?.links().filter((edge) => edge.visible).length ?? 0,
        labels: simulation ? visibleLabelIds(simulation.nodes()).size : 0
      }),
      getForceOptions: () => ({ repulsion, linkDistance }),
      getSimulationState: () => ({
        generation: simulationGeneration,
        alpha: round(simulation?.alpha() ?? 0),
        paused: simulation?.isPaused() ?? true
      }),
      getWorldState: graphWorldState
    };
  }

  function uninstallTestApi() {
    if (typeof window === 'undefined') return;
    delete (window as GraphWindow).__pkmGraphTest;
  }

  function serializeNode(node: GraphSimulationNode | null) {
    if (!node) return null;
    return {
      id: node.id,
      label: node.label,
      type: node.type,
      x: round(node.x),
      y: round(node.y),
      radius: round(node.radius),
      degree: node.degree,
      hub: node.hub,
      visible: node.visible
    };
  }

  function serializeEdge(edge: GraphSimulationLink | null) {
    if (!edge) return null;
    return {
      source: linkId(edge.source),
      target: linkId(edge.target),
      type: edge.type,
      distance: round(edge.distance),
      confidence: round(edge.confidence),
      visible: edge.visible
    };
  }

  function linkNode(value: string | GraphSimulationNode, byId: Map<string, GraphSimulationNode>) {
    return typeof value === 'string' ? byId.get(value) : value;
  }

  function linkId(value: string | GraphSimulationNode) {
    return typeof value === 'string' ? value : value.id;
  }

  function canvasSize() {
    const rect = canvas?.getBoundingClientRect();
    return {
      width: Math.max(1, rect?.width ?? GRAPH_FALLBACK_WIDTH),
      height: Math.max(1, rect?.height ?? GRAPH_FALLBACK_HEIGHT)
    };
  }

  function graphWorldSize(size: { width: number; height: number }, nodeCount: number) {
    const spread = Math.max(1, Math.sqrt(Math.max(1, nodeCount)));
    return {
      width: Math.round(Math.max(GRAPH_FALLBACK_WIDTH, size.width * GRAPH_WORLD_VIEWPORT_SCALE, spread * GRAPH_WORLD_NODE_SPACING_X)),
      height: Math.round(Math.max(GRAPH_FALLBACK_HEIGHT, size.height * GRAPH_WORLD_VIEWPORT_SCALE, spread * GRAPH_WORLD_NODE_SPACING_Y))
    };
  }

  function graphWorldState() {
    return {
      ...graphWorld,
      nodeBounds: nodeBounds(simulation?.nodes() ?? [])
    };
  }

  function nodeBounds(nodes: GraphSimulationNode[]) {
    if (nodes.length === 0) return { minX: 0, minY: 0, maxX: 0, maxY: 0 };
    return nodes.reduce(
      (bounds, node) => ({
        minX: Math.min(bounds.minX, round(node.x)),
        minY: Math.min(bounds.minY, round(node.y)),
        maxX: Math.max(bounds.maxX, round(node.x)),
        maxY: Math.max(bounds.maxY, round(node.y))
      }),
      { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity }
    );
  }

  function searchGraphNodes(nodes: NormalizedGraphNode[], query: string) {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return nodes
      .filter((node) => node.label.toLowerCase().includes(q) || node.id.toLowerCase().includes(q))
      .sort(compareGraphImportance)
      .slice(0, 8);
  }

  function accessibilityStatus() {
    const focused = focusedNode;
    if (!focused) return `Graph ready. ${interactiveGraph.nodes.length} nodes. Focus: full graph.`;
    const neighborCount = [...focusStates.values()].filter((state) => state === 'neighbor').length;
    const previewState = preview ? 'Preview open.' : 'Preview closed.';
    return `Focus: ${focused.label}. ${neighborCount} neighbors. ${previewState}`;
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

  function graphPalette() {
    const dark = typeof document !== 'undefined' && document.documentElement.dataset.theme === 'dark';
    return {
      note: dark ? '#6b7280' : '#374151',
      tag: '#0f766e',
      hub: '#2563eb',
      unresolved: '#9a3412',
      noteStroke: dark ? '#cbd5e1' : '#111827',
      edge: dark ? '#64748b' : '#94a3b8',
      semanticEdge: dark ? '#a78bfa' : '#7c3aed',
      accent: '#eab308',
      label: dark ? '#e5e7eb' : '#111827'
    };
  }

  function nodeColor(node: NormalizedGraphNode, palette: ReturnType<typeof graphPalette>) {
    if (node.hub) return palette.hub;
    if (node.type === 'tag') return palette.tag;
    if (node.type === 'note_or_unresolved') return palette.unresolved;
    return palette.note;
  }

  function nodeStroke(node: NormalizedGraphNode, palette: ReturnType<typeof graphPalette>) {
    if (node.hub) return '#93c5fd';
    return palette.noteStroke;
  }

  function stringValue(value: unknown) {
    return typeof value === 'string' ? value : '';
  }

  function round(value: number) {
    return Math.round(value * 100) / 100;
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<svelte:head>
  <title>Graph - {vaultName} - pkm</title>
</svelte:head>

<main class="graph-page">
  {#if loading}
    <section class="graph-layout" data-testid="graph-layout" data-preview-open="false">
      <div class="graph-stage">
        <p class="graph-summary" data-testid="graph-summary">Loading graph...</p>
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

        <div class="graph-controls" data-testid="graph-controls" aria-label="Graph controls">
          <label class="search-control">
            <span>Search</span>
            <input
              type="search"
              aria-label="Search graph nodes"
              bind:value={searchQuery}
              placeholder="node or tag"
            />
          </label>
          <div class="control-buttons">
            <button type="button" aria-label="Zoom out" onclick={() => zoomBy(-0.1)}>−</button>
            <button type="button" aria-label="Zoom in" onclick={() => zoomBy(0.1)}>+</button>
            <button type="button" onclick={resetView}>Fit</button>
            <button type="button" onclick={setPaused}>{paused ? 'Resume' : 'Pause'}</button>
          </div>
          <div class="force-controls" aria-label="Force controls">
            <label>
              <span>Repulsion</span>
              <input
                type="range"
                min="-900"
                max="-80"
                step="20"
                value={repulsion}
                aria-label="Repulsion strength"
                oninput={updateRepulsion}
              />
              <output>{Math.abs(repulsion)}</output>
            </label>
            <label>
              <span>Link distance</span>
              <input
                type="range"
                min="52"
                max="180"
                step="4"
                value={linkDistance}
                aria-label="Link distance"
                oninput={updateLinkDistance}
              />
              <output>{linkDistance}</output>
            </label>
          </div>
        </div>

        {#if searchResults.length}
          <div class="search-results" aria-label="Graph search results">
            {#each searchResults as result (result.id)}
              <button type="button" onclick={() => focusNode(result)}>Focus {result.label}</button>
            {/each}
          </div>
        {/if}

        <p class="sr-status" data-testid="graph-a11y-status" aria-live="polite">{a11yStatus}</p>

        {#if focusedNode}
          <div class="focus-panel" aria-label="Focused graph node">
            <span>{focusedNode.label}</span>
            {#if focusedNode.type === 'note'}
              <button type="button" onclick={() => void openPreview(focusedNode)}>Preview focused note</button>
            {/if}
          </div>
        {/if}

        <div class="force-surface" data-testid="graph-force-surface" role="application" aria-label="Vault graph">
          <canvas
            bind:this={canvas}
            class="graph-canvas"
            data-testid="graph-canvas"
            aria-label="Interactive vault graph canvas"
            onwheel={handleWheel}
            onpointerdown={handlePointerDown}
            onpointermove={handlePointerMove}
            onpointerup={(event) => void handlePointerUp(event)}
            onpointercancel={handlePointerCancel}
            onpointerleave={handlePointerCancel}
          ></canvas>
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
    height: calc(100dvh - 58px);
    min-height: 560px;
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
    font-weight: 700;
  }

  .graph-layout {
    display: grid;
    height: 100%;
    min-height: 0;
    grid-template-columns: minmax(0, 1fr);
    background: var(--bg);
  }

  .graph-layout.preview-open {
    grid-template-columns: minmax(0, 1fr) minmax(340px, 42vw);
  }

  .graph-stage {
    display: flex;
    min-width: 0;
    min-height: 0;
    flex-direction: column;
    padding: 8px 10px 0;
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
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
    padding: 8px 0;
    border-top: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
  }

  .search-control {
    display: grid;
    gap: 5px;
    min-width: min(280px, 58vw);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 11px;
    text-transform: uppercase;
  }

  .search-control input {
    border: 1px solid var(--border);
    border-radius: var(--radius-sm, 2px);
    padding: 8px 9px;
    color: var(--text);
    background: var(--surface);
    font: inherit;
    text-transform: none;
  }

  .control-buttons,
  .force-controls,
  .search-results,
  .focus-panel {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .force-controls {
    align-items: end;
    max-width: min(520px, 100%);
  }

  .force-controls label {
    display: grid;
    grid-template-columns: auto minmax(96px, 150px) 32px;
    align-items: center;
    gap: 7px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 11px;
    text-transform: uppercase;
  }

  .force-controls input {
    accent-color: var(--accent);
  }

  .force-controls output {
    color: var(--text);
    font-size: 11px;
    text-align: right;
  }

  .control-buttons button,
  .search-results button,
  .focus-panel button,
  .open-note {
    min-height: 30px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm, 2px);
    padding: 0 10px;
    color: var(--text);
    background: var(--surface-raised);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 12px;
  }

  .search-results,
  .focus-panel {
    margin-bottom: 8px;
    color: var(--text-muted);
    font-size: 13px;
  }

  .focus-panel {
    align-items: center;
  }

  .force-surface {
    position: relative;
    min-height: 0;
    flex: 1;
    width: 100%;
    border: 0;
    background: transparent;
    overflow: hidden;
    touch-action: none;
  }

  .graph-canvas {
    display: block;
    width: 100%;
    height: 100%;
    min-height: 0;
    cursor: grab;
  }

  .graph-canvas:active {
    cursor: grabbing;
  }

  .sr-status {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
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
    padding: 0;
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
      padding: 8px 8px 0;
    }

    .graph-topline,
    .graph-controls {
      align-items: flex-start;
      flex-direction: column;
      gap: 6px;
    }

    .control-buttons button {
      flex: 1;
    }

    .preview-sheet {
      border-top: 1px solid var(--border);
      border-left: 0;
      box-shadow: 0 -10px 22px rgb(0 0 0 / 0.18);
    }
  }
</style>
