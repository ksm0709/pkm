import {
  screenToWorld,
  type GraphPoint,
  type GraphTransform,
} from "./viewport";

export type HittableGraphNode = {
  id: string;
  x: number;
  y: number;
  radius: number;
  visible?: boolean;
};

export function hitTestNode<T extends HittableGraphNode>(
  nodes: T[],
  screenPoint: GraphPoint,
  transform: GraphTransform,
  padding = 4,
): T | null {
  const world = screenToWorld(screenPoint, transform);
  let best: { node: T; distance: number } | null = null;

  for (const node of nodes) {
    if (node.visible === false) continue;
    const distance = Math.hypot(world.x - node.x, world.y - node.y);
    const threshold = Math.max(8, node.radius + padding);
    if (distance > threshold) continue;
    if (!best || distance < best.distance) best = { node, distance };
  }

  return best?.node ?? null;
}
