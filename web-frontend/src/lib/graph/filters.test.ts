import { describe, expect, it } from 'vitest';
import {
  applyGraphTypeFilters,
  collectGraphTypes,
  defaultGraphTypeFilters,
  toggleGraphType,
  type GraphData
} from './filters';

const graph: GraphData = {
  directed: true,
  multigraph: false,
  graph: {},
  nodes: [
    { id: 'alpha', type: 'note', title: 'Alpha' },
    { id: 'beta', type: 'note', title: 'Beta' },
    { id: 'tag:pkm', type: 'tag', name: 'pkm' },
    { id: 'missing-note', type: 'note_or_unresolved', title: 'Missing Note' },
    { id: 'legacy' }
  ],
  links: [
    { source: 'alpha', target: 'beta', type: 'wikilink' },
    { source: 'alpha', target: 'tag:pkm', type: 'has_tag' },
    { source: 'beta', target: 'missing-note', type: 'wikilink' },
    { source: { id: 'legacy' }, target: 'alpha' }
  ]
};

describe('graph type filters', () => {
  it('collects deterministic node and edge type options', () => {
    expect(collectGraphTypes(graph)).toEqual({
      nodeTypes: ['note', 'note_or_unresolved', 'tag', 'unknown'],
      edgeTypes: ['has_tag', 'wikilink', 'unknown']
    });
  });

  it('defaults to every discovered node and edge type', () => {
    const filters = defaultGraphTypeFilters(graph);

    expect([...filters.nodeTypes]).toEqual(['note', 'note_or_unresolved', 'tag', 'unknown']);
    expect([...filters.edgeTypes]).toEqual(['has_tag', 'wikilink', 'unknown']);
    expect(applyGraphTypeFilters(graph, filters)).toMatchObject({
      nodes: graph.nodes,
      links: graph.links
    });
  });

  it('filters nodes by selected node types and drops orphaned edges', () => {
    const filtered = applyGraphTypeFilters(graph, {
      nodeTypes: new Set(['note']),
      edgeTypes: new Set(['has_tag', 'wikilink', 'unknown'])
    });

    expect(filtered.nodes.map((node) => node.id)).toEqual(['alpha', 'beta']);
    expect(filtered.links).toEqual([{ source: 'alpha', target: 'beta', type: 'wikilink' }]);
  });

  it('filters edges by selected edge types while preserving matching nodes', () => {
    const filtered = applyGraphTypeFilters(graph, {
      nodeTypes: new Set(['note', 'note_or_unresolved', 'tag', 'unknown']),
      edgeTypes: new Set(['wikilink'])
    });

    expect(filtered.nodes).toHaveLength(5);
    expect(filtered.links.map((link) => link.type)).toEqual(['wikilink', 'wikilink']);
  });

  it('toggles filter selections without mutating the original set', () => {
    const original = new Set(['note', 'tag']);

    expect([...toggleGraphType(original, 'tag')]).toEqual(['note']);
    expect([...original]).toEqual(['note', 'tag']);
    expect([...toggleGraphType(original, 'note_or_unresolved')]).toEqual([
      'note',
      'tag',
      'note_or_unresolved'
    ]);
  });
});
