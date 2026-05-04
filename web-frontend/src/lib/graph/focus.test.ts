import { describe, expect, it } from 'vitest';
import { normalizeGraph } from './normalize';
import { focusNeighborhood, graphFocusState } from './focus';

const graph = normalizeGraph({
  nodes: [
    { id: 'project-plan', type: 'note' },
    { id: 'architecture', type: 'note' },
    { id: 'journal', type: 'note' },
    { id: 'daily-log', type: 'note' }
  ],
  edges: [
    { source: 'project-plan', target: 'architecture' },
    { source: 'architecture', target: 'journal' },
    { source: 'journal', target: 'daily-log' }
  ]
});

describe('graph focus helpers', () => {
  it('returns a depth-limited neighborhood around the focused node', () => {
    expect([...focusNeighborhood(graph, 'project-plan', 1)]).toEqual(['architecture', 'project-plan']);
    expect([...focusNeighborhood(graph, 'project-plan', 2)]).toEqual([
      'architecture',
      'journal',
      'project-plan'
    ]);
  });

  it('keeps global nodes present while marking non-neighborhood nodes muted', () => {
    const states = graphFocusState(graph, 'project-plan', 1);

    expect(states.get('project-plan')).toBe('focused');
    expect(states.get('architecture')).toBe('neighbor');
    expect(states.get('journal')).toBe('muted');
    expect(states.get('daily-log')).toBe('muted');
  });
});
