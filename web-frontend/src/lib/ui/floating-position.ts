export interface FloatingPoint {
  x: number;
  y: number;
}

export interface FloatingSize {
  width: number;
  height: number;
}

export interface FloatingViewport {
  width: number;
  height: number;
}

export function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum);
}

export function viewportSize(): FloatingViewport {
  if (typeof window === "undefined") return { width: 1024, height: 768 };
  return {
    width: window.innerWidth || document.documentElement.clientWidth || 1024,
    height: window.innerHeight || document.documentElement.clientHeight || 768,
  };
}

export function floatingSizeForViewport(
  maxSize: FloatingSize,
  viewport: FloatingViewport,
  inset = 8,
) {
  return {
    width: Math.min(maxSize.width, Math.max(0, viewport.width - inset * 4)),
    height: Math.min(maxSize.height, Math.max(0, viewport.height - inset * 4)),
  };
}

export function clampFloatingPosition(
  position: FloatingPoint,
  size: FloatingSize,
  viewport: FloatingViewport,
  inset = 8,
): FloatingPoint {
  const maxX = Math.max(inset, viewport.width - size.width - inset);
  const maxY = Math.max(inset, viewport.height - size.height - inset);
  return {
    x: Math.round(clamp(position.x, inset, maxX)),
    y: Math.round(clamp(position.y, inset, maxY)),
  };
}

export function floatingTopLeftFromAnchor(
  anchor: FloatingPoint,
  size: FloatingSize,
  viewport: FloatingViewport,
  inset = 8,
): FloatingPoint {
  return clampFloatingPosition(
    { x: anchor.x - size.width / 2, y: anchor.y },
    size,
    viewport,
    inset,
  );
}
