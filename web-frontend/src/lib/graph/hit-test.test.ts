import { describe, expect, it } from 'vitest';
import { hitTestNode } from './hit-test';

describe('graph hit testing', () => {
  const nodes = [
    { id: 'a', x: 100, y: 100, radius: 12 },
    { id: 'b', x: 200, y: 100, radius: 18 }
  ];

  it('selects the nearest transformed node within radius', () => {
    expect(hitTestNode(nodes, { x: 204, y: 103 }, { x: 0, y: 0, k: 1 })?.id).toBe('b');
    expect(hitTestNode(nodes, { x: 220, y: 220 }, { x: 20, y: 20, k: 2 })?.id).toBe('a');
  });

  it('returns null when the pointer is outside all nodes', () => {
    expect(hitTestNode(nodes, { x: 500, y: 500 }, { x: 0, y: 0, k: 1 })).toBeNull();
  });
});
