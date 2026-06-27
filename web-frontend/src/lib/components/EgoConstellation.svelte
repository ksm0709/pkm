<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { apiGet } from "$lib/api/client.js";

  interface Props {
    vaultName: string;
    noteId: string;
  }

  interface EgoNode {
    id: string;
    title?: string;
  }

  interface EgoLink {
    source: string;
    target: string;
  }

  interface EgoGraph {
    nodes: EgoNode[];
    links: EgoLink[];
  }

  interface EgoGraphResponse {
    nodes?: EgoNode[];
    links?: EgoLink[];
  }

  interface NodePos {
    id: string;
    title: string;
    x: number;
    y: number;
    isCurrent: boolean;
  }

  interface EdgeLine {
    x1: number;
    y1: number;
    x2: number;
    y2: number;
  }

  let { vaultName, noteId }: Props = $props();

  let graph = $state<EgoGraph | null>(null);
  let loading = $state(true);
  let failed = $state(false);

  // Fixed viewBox — SVG scales horizontally, 120 px tall
  const W = 320;
  const H = 120;
  const CX = W / 2;
  const CY = H / 2;
  const RING_R = 44;

  let otherNodes = $derived(
    graph ? graph.nodes.filter((n) => n.id !== noteId) : [],
  );

  let nodePositions = $derived<NodePos[]>([
    ...(graph
      ? [{ id: noteId, title: "", x: CX, y: CY, isCurrent: true }]
      : []),
    ...otherNodes.map((node, i) => {
      const n = otherNodes.length;
      // Distribute evenly on ring, starting at top (−π/2)
      const angle =
        n === 1 ? -Math.PI / 2 : (2 * Math.PI * i) / n - Math.PI / 2;
      return {
        id: node.id,
        title: node.title ?? node.id,
        x: CX + RING_R * Math.cos(angle),
        y: CY + RING_R * Math.sin(angle),
        isCurrent: false,
      };
    }),
  ]);

  let posMap = $derived(new Map(nodePositions.map((n) => [n.id, n])));

  let edgeLines = $derived<EdgeLine[]>(
    graph
      ? graph.links.flatMap((link) => {
          const src = posMap.get(link.source);
          const tgt = posMap.get(link.target);
          return src && tgt
            ? [{ x1: src.x, y1: src.y, x2: tgt.x, y2: tgt.y }]
            : [];
        })
      : [],
  );

  function normalizeEgoGraph(response: EgoGraphResponse): EgoGraph {
    return {
      nodes: Array.isArray(response.nodes) ? response.nodes : [],
      links: Array.isArray(response.links) ? response.links : [],
    };
  }

  onMount(async () => {
    try {
      const response = await apiGet<EgoGraphResponse>(
        `/api/v1/vault/${vaultName}/graph/ego/${noteId}`,
      );
      graph = normalizeEgoGraph(response);
    } catch {
      failed = true;
    } finally {
      loading = false;
    }
  });

  function navigateTo(node: NodePos) {
    if (node.isCurrent) return;
    goto(`/${vaultName}/notes/${node.id}`);
  }
</script>

{#if !loading && !failed && graph && graph.nodes.length > 1}
  <div
    class="ego-constellation"
    aria-label="Ego constellation — 2-hop note graph"
  >
    <svg
      viewBox="0 0 {W} {H}"
      width="100%"
      height={H}
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <!-- Edges first (drawn under nodes) -->
      {#each edgeLines as edge, i (i)}
        <line
          x1={edge.x1}
          y1={edge.y1}
          x2={edge.x2}
          y2={edge.y2}
          stroke="var(--border)"
          stroke-width="1"
        />
      {/each}

      <!-- Neighbor nodes (ring) -->
      {#each nodePositions as node (node.id)}
        {#if !node.isCurrent}
          <g
            class="ring-node"
            role="button"
            tabindex="0"
            aria-label="Go to {node.title}"
            onclick={() => navigateTo(node)}
            onkeydown={(e) => e.key === "Enter" && navigateTo(node)}
          >
            <circle cx={node.x} cy={node.y} r="3" class="ring-circle" />
          </g>
        {/if}
      {/each}

      <!-- Current note center (drawn on top) -->
      {#each nodePositions as node (node.id + "-center")}
        {#if node.isCurrent}
          <circle
            cx={node.x}
            cy={node.y}
            r="5"
            class="center-circle"
            aria-label="Current note"
          />
        {/if}
      {/each}
    </svg>
  </div>
{/if}

<style>
  .ego-constellation {
    margin-bottom: var(--space-5, 24px);
  }

  svg {
    display: block;
    /* No overflow clip — nodes near edge stay visible */
    overflow: visible;
  }

  .center-circle {
    fill: var(--accent);
    /* No pointer events — current note is not clickable */
    pointer-events: none;
  }

  .ring-node {
    cursor: pointer;
  }

  .ring-circle {
    fill: var(--text-muted);
    transition: fill var(--dur-fast, 120ms) var(--ease-out);
  }

  .ring-node:hover .ring-circle,
  .ring-node:focus .ring-circle {
    fill: var(--accent);
  }

  .ring-node:focus {
    outline: none;
  }
</style>
