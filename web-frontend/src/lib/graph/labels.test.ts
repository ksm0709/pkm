import { describe, expect, it } from 'vitest';
import { labelBudget } from './labels';
import type { PositionedGraphNode } from './layout';

const nodes: PositionedGraphNode[] = [
  {
    id: 'focused',
    label: 'Focused',
    type: 'note',
    description: '',
    community: 'a',
    tier: '',
    raw: {},
    degree: 1,
    hub: false,
    importance: 0.2,
    radius: 8,
    x: 20,
    y: 20,
    vx: 0,
    vy: 0
  },
  {
    id: 'hub',
    label: 'Hub',
    type: 'note',
    description: '',
    community: 'a',
    tier: 'hub',
    raw: {},
    degree: 9,
    hub: true,
    importance: 1,
    radius: 16,
    x: 80,
    y: 80,
    vx: 0,
    vy: 0
  },
  {
    id: 'near',
    label: 'Near',
    type: 'note',
    description: '',
    community: 'a',
    tier: '',
    raw: {},
    degree: 4,
    hub: false,
    importance: 0.6,
    radius: 10,
    x: 120,
    y: 80,
    vx: 0,
    vy: 0
  },
  {
    id: 'far',
    label: 'Far',
    type: 'note',
    description: '',
    community: 'b',
    tier: '',
    raw: {},
    degree: 7,
    hub: false,
    importance: 0.7,
    radius: 11,
    x: 900,
    y: 900,
    vx: 0,
    vy: 0
  },
  {
    id: 'low',
    label: 'Low',
    type: 'note',
    description: '',
    community: 'a',
    tier: '',
    raw: {},
    degree: 0,
    hub: false,
    importance: 0,
    radius: 6,
    x: 140,
    y: 80,
    vx: 0,
    vy: 0
  }
];

describe('graph label helpers', () => {
  it('always includes focused hovered and selected labels before budgeted important labels', () => {
    expect(
      [...labelBudget(nodes, { focusedId: 'focused', hoveredId: 'low', selectedId: 'near', maxLabels: 3 })]
    ).toEqual(['focused', 'low', 'near']);
  });

  it('limits labels to important in-viewport nodes within the budget', () => {
    expect([...labelBudget(nodes, { viewport: { x: 0, y: 0, width: 200, height: 200 }, maxLabels: 2 })]).toEqual([
      'hub',
      'near'
    ]);
  });
});
