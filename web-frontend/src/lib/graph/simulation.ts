import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import type {
  NormalizedGraph,
  NormalizedGraphEdge,
  NormalizedGraphNode,
} from "./normalize";

export type GraphSimulationOptions = {
  width?: number;
  height?: number;
  seed?: string;
  linkDistance?: number;
  chargeStrength?: number;
  chargeRange?: number;
  collisionPadding?: number;
  clusterStrength?: number;
  autoStart?: boolean;
  onTick?: () => void;
};

export type GraphSimulationNode = SimulationNodeDatum &
  NormalizedGraphNode & {
    x: number;
    y: number;
    vx: number;
    vy: number;
    radius: number;
    visible: boolean;
  };

export type GraphSimulationLink = SimulationLinkDatum<GraphSimulationNode> &
  NormalizedGraphEdge & {
    source: string | GraphSimulationNode;
    target: string | GraphSimulationNode;
    distance: number;
    visible: boolean;
  };

export type GraphSimulationController = {
  nodes: () => GraphSimulationNode[];
  links: () => GraphSimulationLink[];
  settle: (ticks?: number) => void;
  pause: () => void;
  resume: () => void;
  reheat: (alpha?: number) => void;
  dispose: () => void;
  isPaused: () => boolean;
  isDisposed: () => boolean;
  alpha: () => number;
  setForceOptions: (options: Partial<GraphSimulationOptions>) => void;
};

const DEFAULT_WIDTH = 1000;
const DEFAULT_HEIGHT = 640;

export function createGraphSimulation(
  graph: NormalizedGraph,
  options: GraphSimulationOptions = {},
): GraphSimulationController {
  const width = options.width ?? DEFAULT_WIDTH;
  const height = options.height ?? DEFAULT_HEIGHT;
  const seed = options.seed ?? "pkm-graph";
  let forceOptions: Required<
    Pick<
      GraphSimulationOptions,
      | "linkDistance"
      | "chargeStrength"
      | "chargeRange"
      | "collisionPadding"
      | "clusterStrength"
    >
  > = {
    linkDistance: options.linkDistance ?? 92,
    chargeStrength: options.chargeStrength ?? -420,
    chargeRange: options.chargeRange ?? 900,
    collisionPadding: options.collisionPadding ?? 6,
    clusterStrength: options.clusterStrength ?? 0.045,
  };
  const nodes = graph.nodes.map((node) =>
    seedSimulationNode(node, width, height, seed),
  );
  const nodeIds = new Set(nodes.map((node) => node.id));
  const links = graph.edges
    .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .map((edge) => ({
      ...edge,
      source: edge.source,
      target: edge.target,
      distance: edgeTargetDistance(edge, forceOptions.linkDistance),
      visible: true,
    }));
  const centers = communityCenters(nodes, width, height, seed);
  let paused = false;
  let disposed = false;

  const simulation = forceSimulation<GraphSimulationNode>(nodes)
    .randomSource(seedRandom(seed))
    .force(
      "link",
      forceLink<GraphSimulationNode, GraphSimulationLink>(links)
        .id((node) => node.id)
        .distance((link) => link.distance)
        .strength((link) => edgeStrength(link)),
    )
    .force(
      "charge",
      forceManyBody<GraphSimulationNode>()
        .strength(forceOptions.chargeStrength)
        .distanceMin(4)
        .distanceMax(forceOptions.chargeRange)
        .theta(0.6),
    )
    .force(
      "collision",
      forceCollide<GraphSimulationNode>()
        .radius((node) => node.radius + forceOptions.collisionPadding)
        .iterations(2),
    )
    .force("x", forceX<GraphSimulationNode>(width / 2).strength(0.025))
    .force("y", forceY<GraphSimulationNode>(height / 2).strength(0.025))
    .force("center", forceCenter(width / 2, height / 2))
    .force("cluster", communityForce(centers, forceOptions.clusterStrength))
    .velocityDecay(0.42)
    .on("tick", () => {
      options.onTick?.();
    });

  if (options.autoStart === false) simulation.stop();

  return {
    nodes: () => nodes,
    links: () => links,
    settle(ticks = 120) {
      for (let i = 0; i < ticks; i += 1) simulation.tick();
      options.onTick?.();
    },
    pause() {
      paused = true;
      simulation.stop();
    },
    resume() {
      if (disposed) return;
      paused = false;
      simulation.restart();
    },
    reheat(alpha = 0.35) {
      if (disposed) return;
      simulation.alphaTarget(alpha).restart();
      windowSafeTimeout(() => simulation.alphaTarget(0), 600);
    },
    dispose() {
      disposed = true;
      paused = true;
      simulation.stop();
      simulation.on("tick", null);
    },
    isPaused: () => paused,
    isDisposed: () => disposed,
    alpha: () => simulation.alpha(),
    setForceOptions(next) {
      forceOptions = { ...forceOptions, ...definedForceOptions(next) };
      const link = simulation.force("link") as
        | ReturnType<typeof forceLink<GraphSimulationNode, GraphSimulationLink>>
        | undefined;
      const charge = simulation.force("charge") as
        | ReturnType<typeof forceManyBody<GraphSimulationNode>>
        | undefined;
      const collide = simulation.force("collision") as
        | ReturnType<typeof forceCollide<GraphSimulationNode>>
        | undefined;
      const cluster = simulation.force("cluster") as ClusterForce | undefined;

      if (link) {
        for (const graphLink of links)
          graphLink.distance = edgeTargetDistance(
            graphLink,
            forceOptions.linkDistance,
          );
        link.distance((graphLink) => graphLink.distance);
      }
      if (charge) {
        charge.strength(forceOptions.chargeStrength);
        charge.distanceMax(forceOptions.chargeRange);
      }
      if (collide) {
        collide.radius((node) => node.radius + forceOptions.collisionPadding);
      }
      if (cluster) cluster.strength(forceOptions.clusterStrength);
      simulation.alpha(0.35).restart();
    },
  };
}

function definedForceOptions(
  options: Partial<GraphSimulationOptions>,
): Partial<GraphSimulationOptions> {
  return Object.fromEntries(
    Object.entries(options).filter(([, value]) => value !== undefined),
  ) as Partial<GraphSimulationOptions>;
}

export function edgeTargetDistance(
  edge: Pick<NormalizedGraphEdge, "type" | "confidence">,
  base = 92,
): number {
  if (edge.type === "semantic_similar" || edge.type === "semantic_similarity") {
    return Math.round(base * 1.45 - clamp01(edge.confidence) * base);
  }
  if (
    edge.type === "has_tag" ||
    edge.type === "tagged_by" ||
    edge.type === "tag_note"
  )
    return Math.round(base * 1.55);
  if (edge.type === "wikilink") return base;
  return Math.round(base * 1.2);
}

export function simulationNodeRadius(
  node: Pick<NormalizedGraphNode, "type" | "degree" | "hub" | "importance">,
): number {
  const base =
    node.type === "tag" ? 9 : node.type === "note_or_unresolved" ? 5 : 7;
  const degreeBonus = Math.sqrt(Math.max(0, node.degree)) * 1.7;
  const importanceBonus = clamp01(node.importance) * 5;
  const hubBonus = node.hub ? 6 : 0;
  return (
    Math.round((base + degreeBonus + importanceBonus + hubBonus) * 10) / 10
  );
}

function seedSimulationNode(
  node: NormalizedGraphNode,
  width: number,
  height: number,
  seed: string,
): GraphSimulationNode {
  const community = node.community || node.type || "unknown";
  const base = randomUnit(`${seed}:${community}`);
  const jitter = randomUnit(`${seed}:${community}:${node.id}`);
  const angle = base * Math.PI * 2 + jitter * 0.9;
  const radius = Math.min(width, height) * (0.12 + jitter * 0.28);

  return {
    ...node,
    radius: simulationNodeRadius(node),
    x: width / 2 + Math.cos(angle) * radius,
    y: height / 2 + Math.sin(angle) * radius,
    vx: 0,
    vy: 0,
    visible: true,
  };
}

function edgeStrength(
  edge: Pick<NormalizedGraphEdge, "type" | "weight" | "confidence">,
): number {
  const base = 0.08 + Math.max(0, edge.weight) * 0.035;
  if (edge.type === "semantic_similar" || edge.type === "semantic_similarity")
    return base + clamp01(edge.confidence) * 0.12;
  if (
    edge.type === "has_tag" ||
    edge.type === "tagged_by" ||
    edge.type === "tag_note"
  )
    return base * 0.55;
  return base;
}

type ClusterForce = {
  (alpha: number): void;
  initialize: (nodes: GraphSimulationNode[]) => void;
  strength: (value: number) => ClusterForce;
};

function communityForce(
  centers: Map<string, { x: number; y: number }>,
  initialStrength: number,
): ClusterForce {
  let nodes: GraphSimulationNode[] = [];
  let strength = initialStrength;
  const force = ((alpha: number) => {
    for (const node of nodes) {
      const center = centers.get(node.community || node.type || "unknown");
      if (!center) continue;
      node.vx =
        (node.vx ?? 0) + (center.x - (node.x ?? center.x)) * strength * alpha;
      node.vy =
        (node.vy ?? 0) + (center.y - (node.y ?? center.y)) * strength * alpha;
    }
  }) as ClusterForce;
  force.initialize = (nextNodes: GraphSimulationNode[]) => {
    nodes = nextNodes;
  };
  force.strength = (value: number) => {
    strength = value;
    return force;
  };
  return force;
}

function communityCenters(
  nodes: NormalizedGraphNode[],
  width: number,
  height: number,
  seed: string,
) {
  const communities = [
    ...new Set(nodes.map((node) => node.community || node.type || "unknown")),
  ].sort((a, b) => a.localeCompare(b));
  const centers = new Map<string, { x: number; y: number }>();
  const ring = Math.min(width, height) * 0.24;

  communities.forEach((community, index) => {
    const angle =
      (index / Math.max(1, communities.length)) * Math.PI * 2 +
      randomUnit(`${seed}:${community}`) * 0.4;
    centers.set(community, {
      x: width / 2 + Math.cos(angle) * ring,
      y: height / 2 + Math.sin(angle) * ring,
    });
  });

  return centers;
}

function seedRandom(seed: string) {
  let state = hash(seed) || 1;
  return () => {
    state = Math.imul(1664525, state) + 1013904223;
    return ((state >>> 0) & 0xffffffff) / 0x100000000;
  };
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

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function clamp01(value: number) {
  return clamp(value, 0, 1);
}

function windowSafeTimeout(callback: () => void, ms: number) {
  if (typeof window === "undefined") return setTimeout(callback, ms);
  return window.setTimeout(callback, ms);
}
