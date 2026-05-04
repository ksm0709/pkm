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
  hub: boolean;
  importance: number;
  radius: number;
}

export interface NormalizedGraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  label: string;
  raw: Record<string, unknown>;
  confidence: number;
  weight: number;
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

  const maxDegree = Math.max(1, ...nodes.map((node) => degree.get(node.id) ?? 0));
  const nodesWithDegree = nodes.map((node) => {
    const nodeDegree = degree.get(node.id) ?? 0;
    const normalizedDegree = nodeDegree / maxDegree;
    const hub = node.tier === 'hub' || (nodeDegree >= 3 && normalizedDegree >= 0.75);
    const importance = clamp01(hub ? 1 : normalizedDegree);
    const radius = nodeRadius(node.type, importance, hub);

    return {
      ...node,
      degree: nodeDegree,
      hub,
      importance,
      radius
    };
  });

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
  const cluster =
    stringFrom(entry.community) ||
    stringFrom(entry.cluster) ||
    firstString(entry.clusters) ||
    firstString(entry.top_tags) ||
    stringFrom(entry.group) ||
    type;
  const tier = stringFrom(entry.graph_tier) || stringFrom(entry.tier) || '';

  return {
    id,
    label,
    type,
    description: stringFrom(entry.description) || stringFrom(entry.summary) || '',
    community: cluster,
    tier,
    raw: entry,
    degree: 0,
    hub: false,
    importance: 0,
    radius: nodeRadius(type, 0, false)
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
    raw: entry,
    confidence: confidenceFrom(entry),
    weight: weightFrom(entry, type)
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

function firstString(value: unknown): string {
  if (!Array.isArray(value)) return '';
  for (const entry of value) {
    const text = stringFrom(entry);
    if (text) return text;
  }
  return '';
}

function numberFrom(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function confidenceFrom(entry: Record<string, unknown>): number {
  return clamp01(numberFrom(entry.confidence) ?? numberFrom(entry.score) ?? numberFrom(entry.similarity) ?? 0.5);
}

function weightFrom(entry: Record<string, unknown>, type: string): number {
  const explicit = numberFrom(entry.weight) ?? numberFrom(entry.strength);
  if (explicit !== null) return Math.max(0, explicit);

  if (type === 'semantic_similar' || type === 'semantic_similarity') return 1.4;
  if (type === 'has_tag' || type === 'tagged_by' || type === 'tag_note') return 0.9;
  if (type === 'wikilink') return 1.2;
  return 1;
}

function nodeRadius(type: string, importance: number, hub: boolean): number {
  const base = type === 'tag' ? 7 : type === 'note_or_unresolved' ? 5 : 6;
  const bonus = hub ? 6 : 0;
  return Math.round((base + importance * 8 + bonus) * 10) / 10;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
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
