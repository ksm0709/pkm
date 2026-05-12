import type { PositionedGraphNode } from "./layout";

export interface GraphViewport {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface LabelBudgetOptions {
  focusedId?: string | null;
  hoveredId?: string | null;
  selectedId?: string | null;
  viewport?: GraphViewport;
  maxLabels?: number;
}

export function labelBudget(
  nodes: PositionedGraphNode[],
  options: LabelBudgetOptions = {},
): Set<string> {
  const maxLabels = Math.max(0, options.maxLabels ?? 24);
  const labels = new Set<string>();
  const pinned = [
    options.focusedId,
    options.hoveredId,
    options.selectedId,
  ].filter(Boolean) as string[];

  for (const id of pinned) {
    if (labels.size >= maxLabels) return labels;
    if (nodes.some((node) => node.id === id)) labels.add(id);
  }

  const candidates = nodes
    .filter((node) => !labels.has(node.id))
    .filter((node) => inViewport(node, options.viewport))
    .filter((node) => node.hub || node.importance >= 0.45 || node.degree >= 3)
    .sort(
      (a, b) =>
        Number(b.hub) - Number(a.hub) ||
        b.importance - a.importance ||
        b.degree - a.degree ||
        a.label.localeCompare(b.label) ||
        a.id.localeCompare(b.id),
    );

  for (const node of candidates) {
    if (labels.size >= maxLabels) break;
    labels.add(node.id);
  }

  return labels;
}

function inViewport(
  node: PositionedGraphNode,
  viewport?: GraphViewport,
): boolean {
  if (!viewport) return true;
  return (
    node.x >= viewport.x &&
    node.x <= viewport.x + viewport.width &&
    node.y >= viewport.y &&
    node.y <= viewport.y + viewport.height
  );
}
