export interface GraphNode {
  id: string;
  type?: string | null;
  title?: string | null;
  name?: string | null;
  [key: string]: unknown;
}

export interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  type?: string | null;
  [key: string]: unknown;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  [key: string]: unknown;
}

export interface GraphTypeFilters {
  nodeTypes: ReadonlySet<string>;
  edgeTypes: ReadonlySet<string>;
}

const UNKNOWN_TYPE = 'unknown';

export function graphNodeType(node: GraphNode): string {
  return normalizeType(node.type);
}

export function graphEdgeType(link: GraphLink): string {
  return normalizeType(link.type);
}

export function graphEndpointId(endpoint: string | GraphNode): string {
  return typeof endpoint === 'string' ? endpoint : endpoint.id;
}

export function collectGraphTypes(graph: GraphData | null | undefined) {
  const nodeTypes = new Set<string>();
  const edgeTypes = new Set<string>();

  for (const node of graph?.nodes ?? []) {
    nodeTypes.add(graphNodeType(node));
  }

  for (const link of graph?.links ?? []) {
    edgeTypes.add(graphEdgeType(link));
  }

  return {
    nodeTypes: [...nodeTypes].sort(compareTypes),
    edgeTypes: [...edgeTypes].sort(compareTypes)
  };
}

export function defaultGraphTypeFilters(graph: GraphData | null | undefined): GraphTypeFilters {
  const { nodeTypes, edgeTypes } = collectGraphTypes(graph);
  return {
    nodeTypes: new Set(nodeTypes),
    edgeTypes: new Set(edgeTypes)
  };
}

export function applyGraphTypeFilters(
  graph: GraphData | null | undefined,
  filters: GraphTypeFilters
): GraphData {
  if (!graph) return { nodes: [], links: [] };

  const nodes = graph.nodes.filter((node) => filters.nodeTypes.has(graphNodeType(node)));
  const visibleNodeIds = new Set(nodes.map((node) => node.id));
  const links = graph.links.filter((link) => {
    if (!filters.edgeTypes.has(graphEdgeType(link))) return false;
    return visibleNodeIds.has(graphEndpointId(link.source)) && visibleNodeIds.has(graphEndpointId(link.target));
  });

  return { ...graph, nodes, links };
}

export function toggleGraphType(types: ReadonlySet<string>, type: string): Set<string> {
  const next = new Set(types);
  if (next.has(type)) {
    next.delete(type);
  } else {
    next.add(type);
  }
  return next;
}

function normalizeType(type: string | null | undefined) {
  const normalized = type?.trim();
  return normalized || UNKNOWN_TYPE;
}

function compareTypes(a: string, b: string) {
  if (a === UNKNOWN_TYPE && b !== UNKNOWN_TYPE) return 1;
  if (b === UNKNOWN_TYPE && a !== UNKNOWN_TYPE) return -1;
  return a.localeCompare(b);
}
