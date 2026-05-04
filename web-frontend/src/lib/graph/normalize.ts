export type RawGraphNodeKind = 'note' | 'tag' | 'note_or_unresolved';

export interface RawGraphNode {
  id?: unknown;
  title?: unknown;
  name?: unknown;
  label?: unknown;
  description?: unknown;
  type?: unknown;
  community?: unknown;
  cluster?: unknown;
  graph_tier?: unknown;
}

export interface RawGraphEdge {
  source?: unknown;
  target?: unknown;
  type?: unknown;
}

export interface RawGraphPayload {
  nodes?: unknown;
  links?: unknown;
  edges?: unknown;
}

export interface NormalizedNode {
  id: string;
  title: string;
  description: string;
  type: RawGraphNodeKind;
  community?: string;
  cluster?: string;
  graph_tier?: string;
}

export interface NormalizedEdge {
  id: string;
  source: string;
  target: string;
  type?: string;
}

export interface NormalizedGraph {
  nodes: NormalizedNode[];
  edges: NormalizedEdge[];
}

function nodeIdFromRef(value: unknown): string | null {
  if (typeof value === 'string' || typeof value === 'number') {
    const raw = String(value).trim();
    return raw.length ? raw : null;
  }

  if (!value || typeof value !== 'object') return null;

  const rec = value as { id?: unknown; node_id?: unknown };
  const raw =
    (rec as { id?: unknown }).id ??
    (rec as { node_id?: unknown }).node_id ??
    (value as { source?: unknown }).source ??
    null;

  if (typeof raw === 'string' || typeof raw === 'number') {
    const text = String(raw).trim();
    return text.length ? text : null;
  }

  return null;
}

function toText(value: unknown): string | undefined {
  if (typeof value === 'string' && value.trim()) return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return undefined;
}

function normalizeNodeKind(value: unknown): RawGraphNodeKind {
  if (value === 'tag') return 'tag';
  if (value === 'note_or_unresolved') return 'note_or_unresolved';
  return 'note';
}

function normalizeEdges(rawEdges: unknown): NormalizedEdge[] {
  if (!Array.isArray(rawEdges)) return [];

  const edges: NormalizedEdge[] = [];

  rawEdges.forEach((entry, index) => {
    if (!entry || typeof entry !== 'object') return;
    const raw = entry as RawGraphEdge;

    const source = nodeIdFromRef(raw.source);
    const target = nodeIdFromRef(raw.target);
    if (!source || !target) return;

    edges.push({
      id: `${source}->${target}::${index}`,
      source,
      target,
      type: toText((entry as RawGraphEdge).type)
    });
  });

  return edges;
}

export function normalizeGraph(raw: RawGraphPayload): NormalizedGraph {
  const rawNodes = Array.isArray(raw?.nodes) ? raw.nodes : [];

  const normalizedNodes = rawNodes
    .filter((entry): entry is RawGraphNode => !!entry && typeof entry === 'object')
    .map((entry) => {
      const id = nodeIdFromRef(entry);
      if (!id) return null;

      return {
        id,
        title: toText(entry.title) ?? toText(entry.name) ?? toText(entry.label) ?? id,
        description: toText(entry.description) ?? '',
        type: normalizeNodeKind(entry.type),
        community: toText(entry.community),
        cluster: toText(entry.cluster),
        graph_tier: toText(entry.graph_tier)
      } satisfies NormalizedNode;
    })
    .filter((node): node is NormalizedNode => !!node);

  const edges = normalizeEdges(raw?.links ?? raw?.edges);

  return {
    nodes: normalizedNodes,
    edges
  };
}

export function degreesByNode(nodes: NormalizedNode[], edges: NormalizedEdge[]) {
  const counts = new Map<string, number>(nodes.map((node) => [node.id, 0]));

  for (const edge of edges) {
    counts.set(edge.source, (counts.get(edge.source) ?? 0) + 1);
    counts.set(edge.target, (counts.get(edge.target) ?? 0) + 1);
  }

  return (nodeId: string) => counts.get(nodeId) ?? 0;
}

export function filterNodes(nodes: NormalizedNode[], nodeType: string | 'all') {
  return nodeType === 'all' ? nodes : nodes.filter((node) => node.type === nodeType);
}

export function filterEdges(edges: NormalizedEdge[], edgeType: string | 'all') {
  return edgeType === 'all' ? edges : edges.filter((edge) => edge.type === edgeType);
}
