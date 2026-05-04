import type { NormalizedGraph, NormalizedGraphEdge, NormalizedGraphNode } from './normalize';

export interface PositionedGraphNode extends NormalizedGraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

export interface GraphLayoutOptions {
  width?: number;
  height?: number;
  ticks?: number;
  seed?: string;
}

export interface GraphLayout {
  tick: (ticks?: number) => void;
  nodes: () => PositionedGraphNode[];
}

const DEFAULT_WIDTH = 900;
const DEFAULT_HEIGHT = 600;

export function semanticEdgeDistance(edge: Pick<NormalizedGraphEdge, 'type' | 'confidence'>): number {
  if (edge.type !== 'semantic_similar' && edge.type !== 'semantic_similarity') return 120;
  return 150 - clamp01(edge.confidence) * 125;
}

export function createGraphLayout(graph: NormalizedGraph, options: GraphLayoutOptions = {}): GraphLayout {
  const width = options.width ?? DEFAULT_WIDTH;
  const height = options.height ?? DEFAULT_HEIGHT;
  const seed = options.seed ?? 'graph';
  const nodes = graph.nodes.map((node) => seedNode(node, width, height, seed));
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const edges = graph.edges
    .map((edge) => ({ edge, source: byId.get(edge.source), target: byId.get(edge.target) }))
    .filter((entry): entry is { edge: NormalizedGraphEdge; source: PositionedGraphNode; target: PositionedGraphNode } =>
      Boolean(entry.source && entry.target)
    );
  const centers = communityCenters(nodes, width, height, seed);

  return {
    tick(ticks = 1) {
      for (let i = 0; i < ticks; i += 1) {
        applyEdgeForces(edges);
        applyClusterGravity(nodes, centers);
        applyCollision(nodes);
        integrate(nodes, width, height);
      }
    },
    nodes() {
      return nodes.map((node) => ({ ...node }));
    }
  };
}

export function settleGraphLayout(graph: NormalizedGraph, options: GraphLayoutOptions = {}): PositionedGraphNode[] {
  const layout = createGraphLayout(graph, options);
  layout.tick(options.ticks ?? 120);
  return layout.nodes().sort((a, b) => a.id.localeCompare(b.id));
}

export function serializeGraphPosition(node: Pick<PositionedGraphNode, 'id' | 'x' | 'y'>): string {
  return `${node.id}:${node.x.toFixed(2)},${node.y.toFixed(2)}`;
}

function seedNode(
  node: NormalizedGraphNode,
  width: number,
  height: number,
  seed: string
): PositionedGraphNode {
  const communityJitter = randomUnit(`${seed}:${node.community}:${node.id}`);
  const angle = randomUnit(`${seed}:${node.community}`) * Math.PI * 2 + communityJitter * 0.8;
  const radius = Math.min(width, height) * (0.18 + communityJitter * 0.22);

  return {
    ...node,
    x: width / 2 + Math.cos(angle) * radius,
    y: height / 2 + Math.sin(angle) * radius,
    vx: 0,
    vy: 0
  };
}

function communityCenters(nodes: PositionedGraphNode[], width: number, height: number, seed: string) {
  const communities = [...new Set(nodes.map((node) => node.community || 'unknown'))].sort((a, b) =>
    a.localeCompare(b)
  );
  const centers = new Map<string, { x: number; y: number }>();
  const ring = Math.min(width, height) * 0.23;

  communities.forEach((community, index) => {
    const angle = (index / Math.max(1, communities.length)) * Math.PI * 2 + randomUnit(`${seed}:${community}`) * 0.4;
    centers.set(community, {
      x: width / 2 + Math.cos(angle) * ring,
      y: height / 2 + Math.sin(angle) * ring
    });
  });

  return centers;
}

function applyEdgeForces(
  edges: Array<{ edge: NormalizedGraphEdge; source: PositionedGraphNode; target: PositionedGraphNode }>
) {
  for (const { edge, source, target } of edges) {
    const dx = target.x - source.x || 0.01;
    const dy = target.y - source.y || 0.01;
    const distance = Math.hypot(dx, dy);
    const desired = semanticEdgeDistance(edge);
    const strength = (0.012 + edge.weight * 0.01 + edge.confidence * 0.01) * (edge.type.includes('semantic') ? 1.8 : 1);
    const force = (distance - desired) * strength;
    const fx = (dx / distance) * force;
    const fy = (dy / distance) * force;

    source.vx += fx;
    source.vy += fy;
    target.vx -= fx;
    target.vy -= fy;
  }
}

function applyClusterGravity(nodes: PositionedGraphNode[], centers: Map<string, { x: number; y: number }>) {
  for (const node of nodes) {
    const center = centers.get(node.community || 'unknown');
    if (!center) continue;
    node.vx += (center.x - node.x) * 0.006;
    node.vy += (center.y - node.y) * 0.006;
  }
}

function applyCollision(nodes: PositionedGraphNode[]) {
  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      const a = nodes[i];
      const b = nodes[j];
      const dx = b.x - a.x || 0.01;
      const dy = b.y - a.y || 0.01;
      const distance = Math.hypot(dx, dy);
      const minimum = a.radius + b.radius + 4;
      if (distance >= minimum) continue;

      const push = ((minimum - distance) / distance) * 0.08;
      const fx = dx * push;
      const fy = dy * push;
      a.vx -= fx;
      a.vy -= fy;
      b.vx += fx;
      b.vy += fy;
    }
  }
}

function integrate(nodes: PositionedGraphNode[], width: number, height: number) {
  for (const node of nodes) {
    node.vx *= 0.78;
    node.vy *= 0.78;
    node.x += node.vx;
    node.y += node.vy;
    node.x = clamp(node.x, node.radius, width - node.radius);
    node.y = clamp(node.y, node.radius, height - node.radius);
  }
}

function randomUnit(input: string): number {
  return (hash(input) % 100000) / 100000;
}

function hash(input: string): number {
  let value = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    value ^= input.charCodeAt(i);
    value = Math.imul(value, 16777619);
  }
  return value >>> 0;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}
