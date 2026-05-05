import { describe, expect, it } from 'vitest';
import type { NormalizedGraph } from './normalize';
import {
  createGraphSimulation,
  edgeTargetDistance,
  simulationNodeRadius,
  type GraphSimulationNode
} from './simulation';

const graph: NormalizedGraph = {
  nodeTypes: ['note', 'tag'],
  edgeTypes: ['wikilink', 'semantic_similar', 'has_tag'],
  nodes: [
    node('alpha', 'Alpha', 'note', 4, true, 'planning'),
    node('beta', 'Beta', 'note', 1, false, 'planning'),
    node('gamma', 'Gamma', 'note', 1, false, 'daily'),
    node('tag:pkm', '#pkm', 'tag', 3, false, 'planning')
  ],
  edges: [
    edge('alpha', 'beta', 'wikilink', 1, 1),
    edge('alpha', 'gamma', 'semantic_similar', 0.92, 1.4),
    edge('beta', 'tag:pkm', 'has_tag', 1, 0.9)
  ]
};

describe('graph force simulation', () => {
  it('maps semantic confidence and tag links to distinct target distances', () => {
    expect(edgeTargetDistance(edge('a', 'b', 'semantic_similar', 0.95, 1.4))).toBeLessThan(
      edgeTargetDistance(edge('a', 'b', 'semantic_similar', 0.2, 1.4))
    );
    expect(edgeTargetDistance(edge('a', 'tag:x', 'has_tag', 1, 0.9))).toBeGreaterThan(
      edgeTargetDistance(edge('a', 'b', 'wikilink', 1, 1))
    );
  });

  it('scales node radius by type, degree, and hub status', () => {
    expect(simulationNodeRadius(node('hub', 'Hub', 'note', 8, true, 'x'))).toBeGreaterThan(
      simulationNodeRadius(node('leaf', 'Leaf', 'note', 1, false, 'x'))
    );
    expect(simulationNodeRadius(node('tag:x', '#x', 'tag', 1, false, 'x'))).toBeGreaterThanOrEqual(9);
  });

  it('creates deterministic seeded positions and keeps coordinates finite while settling', () => {
    const a = createGraphSimulation(graph, { width: 800, height: 500, seed: 'same-seed', autoStart: false });
    const b = createGraphSimulation(graph, { width: 800, height: 500, seed: 'same-seed', autoStart: false });

    expect(snapshot(a.nodes())).toEqual(snapshot(b.nodes()));

    a.settle(80);
    for (const n of a.nodes()) {
      expect(Number.isFinite(n.x)).toBe(true);
      expect(Number.isFinite(n.y)).toBe(true);
    }
    a.dispose();
    b.dispose();
  });

  it('does not clamp graph nodes to the visible viewport rectangle', () => {
    const sim = createGraphSimulation(graph, { width: 800, height: 500, seed: 'free-world', autoStart: false });
    const alpha = sim.nodes().find((n) => n.id === 'alpha');
    expect(alpha).toBeTruthy();

    alpha!.x = 1180;
    alpha!.y = 760;
    alpha!.fx = 1180;
    alpha!.fy = 760;
    sim.settle(2);

    expect(alpha!.x).toBeGreaterThan(800);
    expect(alpha!.y).toBeGreaterThan(500);
    sim.dispose();
  });

  it('exposes pause, resume, reheat, and dispose lifecycle', () => {
    const sim = createGraphSimulation(graph, { width: 800, height: 500, autoStart: false });
    expect(sim.isPaused()).toBe(false);
    sim.pause();
    expect(sim.isPaused()).toBe(true);
    sim.resume();
    expect(sim.isPaused()).toBe(false);
    sim.reheat();
    expect(sim.alpha()).toBeGreaterThan(0);
    sim.dispose();
    expect(sim.isDisposed()).toBe(true);
  });
});

function node(
  id: string,
  label: string,
  type: string,
  degree: number,
  hub: boolean,
  community: string
): NormalizedGraph['nodes'][number] {
  return {
    id,
    label,
    type,
    description: '',
    community,
    tier: hub ? 'hub' : '',
    raw: {},
    degree,
    hub,
    importance: hub ? 1 : degree / 8,
    radius: 6
  };
}

function edge(
  source: string,
  target: string,
  type: string,
  confidence: number,
  weight: number
): NormalizedGraph['edges'][number] {
  return {
    id: `${source}->${target}:${type}`,
    source,
    target,
    type,
    label: type,
    raw: {},
    confidence,
    weight
  };
}

function snapshot(nodes: GraphSimulationNode[]) {
  return nodes.map((n) => [n.id, Math.round(n.x), Math.round(n.y), Math.round(n.radius)]);
}
