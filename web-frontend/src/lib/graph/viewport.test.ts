import { describe, expect, it } from 'vitest';
import {
  fitToBounds,
  panTransform,
  pinchZoomTransform,
  screenToWorld,
  wheelZoomTransform,
  worldToScreen,
  type GraphTransform
} from './viewport';

describe('graph viewport transforms', () => {
  it('round trips world and screen coordinates', () => {
    const transform: GraphTransform = { x: 120, y: -40, k: 1.5 };
    const screen = worldToScreen({ x: 20, y: 30 }, transform);
    expect(screenToWorld(screen, transform)).toEqual({ x: 20, y: 30 });
  });

  it('zooms around the pointer anchor', () => {
    const transform: GraphTransform = { x: 0, y: 0, k: 1 };
    const pointer = { x: 400, y: 300 };
    const worldBefore = screenToWorld(pointer, transform);
    const zoomed = wheelZoomTransform(transform, pointer, -240);
    const worldAfter = screenToWorld(pointer, zoomed);
    expect(zoomed.k).toBeGreaterThan(1);
    expect(worldAfter.x).toBeCloseTo(worldBefore.x, 6);
    expect(worldAfter.y).toBeCloseTo(worldBefore.y, 6);
  });

  it('pinch zooms around the two-finger midpoint', () => {
    const transform: GraphTransform = { x: 80, y: -30, k: 0.5 };
    const midpoint = { x: 180, y: 220 };
    const worldBefore = screenToWorld(midpoint, transform);
    const zoomed = pinchZoomTransform(transform, midpoint, 120, 240);
    const worldAfter = screenToWorld(midpoint, zoomed);

    expect(zoomed.k).toBeCloseTo(1);
    expect(worldAfter.x).toBeCloseTo(worldBefore.x, 6);
    expect(worldAfter.y).toBeCloseTo(worldBefore.y, 6);
  });

  it('pans and fits graph bounds', () => {
    expect(panTransform({ x: 1, y: 2, k: 1 }, 10, -8)).toEqual({ x: 11, y: -6, k: 1 });
    const fit = fitToBounds(
      { minX: 0, minY: 0, maxX: 1000, maxY: 500 },
      { width: 500, height: 300 },
      24
    );
    expect(fit.k).toBeGreaterThan(0);
    expect(fit.k).toBeLessThanOrEqual(1);
  });
});
