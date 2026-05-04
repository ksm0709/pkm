import { describe, expect, it } from 'vitest';
import { normalizeGraph } from './normalize';
import {
  createGraphLayout,
  semanticEdgeDistance,
  serializeGraphPosition,
  settleGraphLayout
} from './layout';

const graph = normalizeGraph({
  nodes: [
    { id: 'alpha', type: 'note', community: 'planning' },
    { id: 'beta', type: 'note', community: 'planning' },
    { id: 'gamma', type: 'note', community: 'daily' }
  ],
  edges: [
    { source: 'alpha', target: 'beta', type: 'semantic_similar', confidence: 0.95 },
    { source: 'alpha', target: 'gamma', type: 'semantic_similar', confidence: 0.2 }
  ]
});

describe('graph force layout helpers', () => {
  it('uses shorter semantic target distance for higher confidence edges', () => {
    expect(semanticEdgeDistance({ type: 'semantic_similar', confidence: 0.95 })).toBeLessThan(
      semanticEdgeDistance({ type: 'semantic_similar', confidence: 0.2 })
    );
    expect(semanticEdgeDistance({ type: 'wikilink', confidence: 0.95 })).toBe(
      semanticEdgeDistance({ type: 'wikilink', confidence: 0.2 })
    );
  });

  it('settles deterministically from seeded node and community positions', () => {
    const first = settleGraphLayout(graph, { width: 600, height: 400, ticks: 80, seed: 'same' });
    const second = settleGraphLayout(graph, { width: 600, height: 400, ticks: 80, seed: 'same' });

    expect(first.map(serializeGraphPosition)).toEqual(second.map(serializeGraphPosition));
    expect(first.every((node) => Number.isFinite(node.x) && Number.isFinite(node.y))).toBe(true);
  });

  it('keeps nodes inside bounds after finite settling', () => {
    const layout = createGraphLayout(graph, { width: 320, height: 240, seed: 'bounds' });
    layout.tick(100);
    const nodes = layout.nodes();

    expect(nodes.every((node) => node.x >= node.radius && node.x <= 320 - node.radius)).toBe(true);
    expect(nodes.every((node) => node.y >= node.radius && node.y <= 240 - node.radius)).toBe(true);
  });

  it('settles high confidence semantic neighbors closer than low confidence neighbors', () => {
    const nodes = settleGraphLayout(graph, { width: 600, height: 400, ticks: 140, seed: 'distance' });
    const byId = new Map(nodes.map((node) => [node.id, node]));
    const alpha = byId.get('alpha');
    const beta = byId.get('beta');
    const gamma = byId.get('gamma');

    expect(alpha && beta && gamma).toBeTruthy();
    const high = Math.hypot((alpha?.x ?? 0) - (beta?.x ?? 0), (alpha?.y ?? 0) - (beta?.y ?? 0));
    const low = Math.hypot((alpha?.x ?? 0) - (gamma?.x ?? 0), (alpha?.y ?? 0) - (gamma?.y ?? 0));

    expect(high).toBeLessThan(low);
  });
});
