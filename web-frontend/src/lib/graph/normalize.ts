export type GraphNodeType = 'note' | 'tag' | 'note_or_unresolved' | string;

export interface NormalizedGraphNode {
  id: string;
  label: string;
  type: GraphNodeType;
  description: string;
  community: string;
  tier: string;
  raw: Record<string, unknown>;
  degree: number;
}

export interface NormalizedGraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  label: string;
  raw: Record<string, unknown>;
}

export interface NormalizedGraph {
  nodes: NormalizedGraphNode[];
  edges: NormalizedGraphEdge[];
  nodeTypes: string[];
  edgeTypes: string[];
}

export function normalizeGraph(raw: unknown): NormalizedGraph {
  const graph = isRecord(raw) ? raw : {};
  const rawNodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const rawEdges = Array.isArray(graph.links)
    ? graph.links
    : Array.isArray(graph.edges)
      ? graph.edges
      : [];

  const nodes = rawNodes
    .map((entry) => normalizeNode(entry))
    .filter((node): node is NormalizedGraphNode => node !== null)
    .sort(compareNode);
  const nodeIds = new Set(nodes.map((node) => node.id));

  const edges = rawEdges
    .map((entry, index) => normalizeEdge(entry, index))
    .filter((edge): edge is NormalizedGraphEdge => edge !== null)
    .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .sort((a, b) => a.source.localeCompare(b.source) || a.target.localeCompare(b.target) || a.type.localeCompare(b.type));

  const degree = new Map<string, number>();
  for (const edge of edges) {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  }

  const nodesWithDegree = nodes.map((node) => ({
    ...node,
    degree: degree.get(node.id) ?? 0
  }));

  return {
    nodes: nodesWithDegree,
    edges,
    nodeTypes: uniqueSorted(nodesWithDegree.map((node) => node.type || 'unknown')),
    edgeTypes: uniqueSorted(edges.map((edge) => edge.type || 'unknown'))
  };
}

function normalizeNode(entry: unknown): NormalizedGraphNode | null {
  if (!isRecord(entry)) return null;
  const id = stringFrom(entry.id) || stringFrom(entry.key) || stringFrom(entry.name) || stringFrom(entry.label);
  if (!id) return null;
  const type = stringFrom(entry.type) || stringFrom(entry.node_type) || stringFrom(entry.kind) || 'note';
  const label = stringFrom(entry.title) || stringFrom(entry.label) || stringFrom(entry.name) || id;
  const cluster = stringFrom(entry.community) || stringFrom(entry.cluster) || stringFrom(entry.group) || type;
  const tier = stringFrom(entry.graph_tier) || stringFrom(entry.tier) || '';

  return {
    id,
    label,
    type,
    description: stringFrom(entry.description) || stringFrom(entry.summary) || '',
    community: cluster,
    tier,
    raw: entry,
    degree: 0
  };
}

function normalizeEdge(entry: unknown, index: number): NormalizedGraphEdge | null {
  if (!isRecord(entry)) return null;
  const source = endpointId(entry.source);
  const target = endpointId(entry.target);
  if (!source || !target) return null;
  const type = stringFrom(entry.type) || stringFrom(entry.edge_type) || stringFrom(entry.relation) || stringFrom(entry.kind) || 'link';
  return {
    id: `${source}->${target}:${type}:${index}`,
    source,
    target,
    type,
    label: stringFrom(entry.label) || type,
    raw: entry
  };
}

function endpointId(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  if (!isRecord(value)) return '';
  return stringFrom(value.id) || stringFrom(value.key) || stringFrom(value.name) || stringFrom(value.label);
}

function stringFrom(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number') return String(value);
  return '';
}

function uniqueSorted(values: string[]) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function compareNode(a: NormalizedGraphNode, b: NormalizedGraphNode) {
  return a.label.localeCompare(b.label) || a.id.localeCompare(b.id);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}
