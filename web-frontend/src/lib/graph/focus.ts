import type { NormalizedGraph } from "./normalize";

export type GraphFocusState = "focused" | "neighbor" | "muted" | "normal";

export function focusNeighborhood(
  graph: NormalizedGraph,
  focusedId: string | null,
  depth = 1,
): Set<string> {
  if (!focusedId || !graph.nodes.some((node) => node.id === focusedId))
    return new Set();

  const adjacency = graphAdjacency(graph);
  const visited = new Set([focusedId]);
  let frontier = [focusedId];

  for (let distance = 0; distance < depth; distance += 1) {
    const next = new Set<string>();
    for (const id of frontier) {
      for (const neighbor of adjacency.get(id) ?? []) {
        if (!visited.has(neighbor)) next.add(neighbor);
      }
    }
    for (const id of next) visited.add(id);
    frontier = [...next].sort((a, b) => a.localeCompare(b));
  }

  return new Set([...visited].sort((a, b) => a.localeCompare(b)));
}

export function graphFocusState(
  graph: NormalizedGraph,
  focusedId: string | null,
  depth = 1,
): Map<string, GraphFocusState> {
  const neighborhood = focusNeighborhood(graph, focusedId, depth);
  const states = new Map<string, GraphFocusState>();

  for (const node of graph.nodes) {
    if (!focusedId) states.set(node.id, "normal");
    else if (node.id === focusedId) states.set(node.id, "focused");
    else if (neighborhood.has(node.id)) states.set(node.id, "neighbor");
    else states.set(node.id, "muted");
  }

  return states;
}

function graphAdjacency(graph: NormalizedGraph): Map<string, string[]> {
  const adjacency = new Map(
    graph.nodes.map((node) => [node.id, [] as string[]]),
  );

  for (const edge of graph.edges) {
    adjacency.get(edge.source)?.push(edge.target);
    adjacency.get(edge.target)?.push(edge.source);
  }

  for (const neighbors of adjacency.values()) {
    neighbors.sort((a, b) => a.localeCompare(b));
  }

  return adjacency;
}
