interface GraphNavigationNode {
  id?: string | null;
  type?: string | null;
}

export function graphNoteHref(vaultName: string, node: GraphNavigationNode | null | undefined) {
  if (!isNavigableGraphNoteNode(node)) return null;
  return `/${encodeURIComponent(vaultName)}/notes/${encodeURIComponent(node.id.trim())}`;
}

export function isNavigableGraphNoteNode(
  node: GraphNavigationNode | null | undefined
): node is GraphNavigationNode & { id: string; type: 'note' } {
  return node?.type === 'note' && typeof node.id === 'string' && node.id.trim().length > 0;
}

export function graphNodeIsInteractive(node: GraphNavigationNode | null | undefined) {
  return isNavigableGraphNoteNode(node);
}
