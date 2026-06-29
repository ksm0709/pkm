// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import {
  createAreaAnnotationFromDrag,
  createTextAnnotationFromSelection,
  overlayStyleForRect,
} from "./annotation-geometry";

function pageElement(page: number, rect: DOMRectInit) {
  const element = document.createElement("section");
  element.className = "pdf-page";
  element.dataset.pageNumber = String(page);
  element.getBoundingClientRect = vi.fn(
    () =>
      ({
        x: rect.x ?? 0,
        y: rect.y ?? 0,
        left: rect.x ?? 0,
        top: rect.y ?? 0,
        width: rect.width ?? 0,
        height: rect.height ?? 0,
        right: (rect.x ?? 0) + (rect.width ?? 0),
        bottom: (rect.y ?? 0) + (rect.height ?? 0),
        toJSON: () => ({}),
      }) as DOMRect,
  );
  return element;
}

describe("PDF annotation geometry", () => {
  it("normalizes an area drag to page-relative coordinates", () => {
    const page = pageElement(2, { x: 100, y: 50, width: 200, height: 400 });

    const annotation = createAreaAnnotationFromDrag({
      page,
      start: { clientX: 120, clientY: 90 },
      end: { clientX: 180, clientY: 210 },
      now: "2026-06-29T08:00:00Z",
      id: "area-1",
    });

    expect(annotation).toEqual({
      id: "area-1",
      type: "area",
      rects: [{ page: 2, x: 0.1, y: 0.1, width: 0.3, height: 0.3 }],
      comment: "",
      created_at: "2026-06-29T08:00:00Z",
      updated_at: "2026-06-29T08:00:00Z",
    });
  });

  it("ignores tiny area drags and clamps drags to page bounds", () => {
    const page = pageElement(1, { x: 100, y: 50, width: 200, height: 400 });

    expect(
      createAreaAnnotationFromDrag({
        page,
        start: { clientX: 120, clientY: 90 },
        end: { clientX: 122, clientY: 91 },
        now: "2026-06-29T08:00:00Z",
        id: "tiny",
      }),
    ).toBeNull();

    const clamped = createAreaAnnotationFromDrag({
      page,
      start: { clientX: 80, clientY: 40 },
      end: { clientX: 350, clientY: 500 },
      now: "2026-06-29T08:00:00Z",
      id: "clamped",
    });

    expect(clamped?.rects[0]).toEqual({
      page: 1,
      x: 0,
      y: 0,
      width: 1,
      height: 1,
    });
  });

  it("builds CSS overlay styles from normalized rects", () => {
    expect(
      overlayStyleForRect({ page: 1, x: 0.1, y: 0.2, width: 0.3, height: 0.4 }),
    ).toContain("left: 10%");
    expect(
      overlayStyleForRect({ page: 1, x: 0.1, y: 0.2, width: 0.3, height: 0.4 }),
    ).toContain("height: 40%");
  });

  it("creates same-page text annotations from browser selection rects", () => {
    const root = document.createElement("div");
    const page = pageElement(3, { x: 100, y: 50, width: 200, height: 400 });
    root.appendChild(page);
    const range = {
      getClientRects: () => [
        {
          left: 120,
          top: 90,
          right: 160,
          bottom: 110,
          width: 40,
          height: 20,
        },
      ],
    };
    const selection = {
      toString: () => "selected words",
      rangeCount: 1,
      getRangeAt: () => range,
    } as unknown as Selection;

    const annotation = createTextAnnotationFromSelection({
      root,
      selection,
      now: "2026-06-29T08:00:00Z",
      id: "text-1",
    });

    expect(annotation).toEqual({
      id: "text-1",
      type: "text",
      rects: [{ page: 3, x: 0.1, y: 0.1, width: 0.2, height: 0.05 }],
      quote: "selected words",
      comment: "",
      created_at: "2026-06-29T08:00:00Z",
      updated_at: "2026-06-29T08:00:00Z",
    });
  });

  it("rejects cross-page text selections for the MVP", () => {
    const root = document.createElement("div");
    root.appendChild(pageElement(1, { x: 0, y: 0, width: 100, height: 100 }));
    root.appendChild(pageElement(2, { x: 0, y: 120, width: 100, height: 100 }));
    const selection = {
      toString: () => "cross page",
      rangeCount: 1,
      getRangeAt: () => ({
        getClientRects: () => [
          { left: 10, top: 10, right: 20, bottom: 20, width: 10, height: 10 },
          { left: 10, top: 130, right: 20, bottom: 140, width: 10, height: 10 },
        ],
      }),
    } as unknown as Selection;

    expect(
      createTextAnnotationFromSelection({
        root,
        selection,
        now: "2026-06-29T08:00:00Z",
        id: "text-cross",
      }),
    ).toBeNull();
  });
});
