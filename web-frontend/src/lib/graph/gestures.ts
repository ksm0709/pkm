import type { GraphNodeType } from './normalize';

export type GraphGestureAction = 'focus' | 'preview' | 'ignore';

export interface GraphGestureInput {
  nodeType: GraphNodeType;
  durationMs: number;
  metaKey?: boolean;
  ctrlKey?: boolean;
  button?: number;
  longPressMs?: number;
}

export function classifyGraphGesture(input: GraphGestureInput): GraphGestureAction {
  if (input.button !== undefined && input.button !== 0) return 'ignore';
  if (input.nodeType !== 'note') return 'focus';

  const previewIntent = Boolean(input.metaKey || input.ctrlKey) || input.durationMs >= (input.longPressMs ?? 500);
  return previewIntent ? 'preview' : 'focus';
}
