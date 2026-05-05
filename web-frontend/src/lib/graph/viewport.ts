export type GraphPoint = { x: number; y: number };
export type GraphSize = { width: number; height: number };
export type GraphBounds = { minX: number; minY: number; maxX: number; maxY: number };

export type GraphTransform = {
  x: number;
  y: number;
  k: number;
};

const MIN_ZOOM = 0.08;
const MAX_ZOOM = 4;

export function worldToScreen(point: GraphPoint, transform: GraphTransform): GraphPoint {
  return {
    x: point.x * transform.k + transform.x,
    y: point.y * transform.k + transform.y
  };
}

export function screenToWorld(point: GraphPoint, transform: GraphTransform): GraphPoint {
  return {
    x: (point.x - transform.x) / transform.k,
    y: (point.y - transform.y) / transform.k
  };
}

export function panTransform(transform: GraphTransform, dx: number, dy: number): GraphTransform {
  return {
    ...transform,
    x: transform.x + dx,
    y: transform.y + dy
  };
}

export function wheelZoomTransform(
  transform: GraphTransform,
  pointer: GraphPoint,
  deltaY: number,
  minZoom = MIN_ZOOM,
  maxZoom = MAX_ZOOM
): GraphTransform {
  const factor = Math.exp(-deltaY * 0.0015);
  const nextK = clamp(transform.k * factor, minZoom, maxZoom);
  const world = screenToWorld(pointer, transform);

  return {
    x: pointer.x - world.x * nextK,
    y: pointer.y - world.y * nextK,
    k: nextK
  };
}

export function zoomAt(
  transform: GraphTransform,
  pointer: GraphPoint,
  nextK: number,
  minZoom = MIN_ZOOM,
  maxZoom = MAX_ZOOM
): GraphTransform {
  const k = clamp(nextK, minZoom, maxZoom);
  const world = screenToWorld(pointer, transform);
  return {
    x: pointer.x - world.x * k,
    y: pointer.y - world.y * k,
    k
  };
}

export function fitToBounds(bounds: GraphBounds, viewport: GraphSize, padding = 24): GraphTransform {
  const graphWidth = Math.max(1, bounds.maxX - bounds.minX);
  const graphHeight = Math.max(1, bounds.maxY - bounds.minY);
  const usableWidth = Math.max(1, viewport.width - padding * 2);
  const usableHeight = Math.max(1, viewport.height - padding * 2);
  const k = clamp(Math.min(usableWidth / graphWidth, usableHeight / graphHeight), MIN_ZOOM, 1);
  const centerX = bounds.minX + graphWidth / 2;
  const centerY = bounds.minY + graphHeight / 2;

  return {
    x: viewport.width / 2 - centerX * k,
    y: viewport.height / 2 - centerY * k,
    k
  };
}

export function clampTransform(transform: GraphTransform, minZoom = MIN_ZOOM, maxZoom = MAX_ZOOM): GraphTransform {
  return {
    x: finiteOr(transform.x, 0),
    y: finiteOr(transform.y, 0),
    k: clamp(finiteOr(transform.k, 1), minZoom, maxZoom)
  };
}

function finiteOr(value: number, fallback: number) {
  return Number.isFinite(value) ? value : fallback;
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}
