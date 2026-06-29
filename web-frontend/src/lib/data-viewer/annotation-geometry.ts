import type { PdfAnnotation, PdfAnnotationRect } from "./annotations";

interface PointLike {
  clientX: number;
  clientY: number;
}

export interface CreateAreaAnnotationOptions {
  page: HTMLElement;
  start: PointLike;
  end: PointLike;
  now: string;
  id: string;
  minPixels?: number;
}

export interface CreateTextAnnotationOptions {
  root: HTMLElement;
  selection: Selection | null;
  now: string;
  id: string;
}

interface ClientRectLike {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

function round(value: number) {
  return Math.round(value * 1_000_000) / 1_000_000;
}

function clamp(value: number, min = 0, max = 1) {
  return Math.min(max, Math.max(min, value));
}

function pageNumberFor(page: HTMLElement) {
  const raw = Number(page.dataset.pageNumber ?? "1");
  return Number.isInteger(raw) && raw >= 1 ? raw : 1;
}

function rectFromPageAndClientRect(
  page: HTMLElement,
  clientRect: ClientRectLike,
): PdfAnnotationRect | null {
  const pageRect = page.getBoundingClientRect();
  if (pageRect.width <= 0 || pageRect.height <= 0) return null;
  const left = clamp((clientRect.left - pageRect.left) / pageRect.width);
  const top = clamp((clientRect.top - pageRect.top) / pageRect.height);
  const right = clamp((clientRect.right - pageRect.left) / pageRect.width);
  const bottom = clamp((clientRect.bottom - pageRect.top) / pageRect.height);
  const width = right - left;
  const height = bottom - top;
  if (width <= 0 || height <= 0) return null;
  return {
    page: pageNumberFor(page),
    x: round(left),
    y: round(top),
    width: round(width),
    height: round(height),
  };
}

function clientRectForDrag(start: PointLike, end: PointLike): ClientRectLike {
  const left = Math.min(start.clientX, end.clientX);
  const top = Math.min(start.clientY, end.clientY);
  const right = Math.max(start.clientX, end.clientX);
  const bottom = Math.max(start.clientY, end.clientY);
  return {
    left,
    top,
    right,
    bottom,
    width: right - left,
    height: bottom - top,
  };
}

export function createAreaAnnotationFromDrag({
  page,
  start,
  end,
  now,
  id,
  minPixels = 4,
}: CreateAreaAnnotationOptions): PdfAnnotation | null {
  const dragRect = clientRectForDrag(start, end);
  if (dragRect.width < minPixels || dragRect.height < minPixels) return null;
  const rect = rectFromPageAndClientRect(page, dragRect);
  if (!rect) return null;
  return {
    id,
    type: "area",
    rects: [rect],
    comment: "",
    created_at: now,
    updated_at: now,
  };
}

function pageContainingRect(
  root: HTMLElement,
  rect: ClientRectLike,
): HTMLElement | null {
  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;
  const pages = Array.from(root.querySelectorAll<HTMLElement>(".pdf-page"));
  return (
    pages.find((page) => {
      const pageRect = page.getBoundingClientRect();
      return (
        centerX >= pageRect.left &&
        centerX <= pageRect.right &&
        centerY >= pageRect.top &&
        centerY <= pageRect.bottom
      );
    }) ?? null
  );
}

export function createTextAnnotationFromSelection({
  root,
  selection,
  now,
  id,
}: CreateTextAnnotationOptions): PdfAnnotation | null {
  const quote = selection?.toString().trim() ?? "";
  if (!selection || selection.rangeCount < 1 || !quote) return null;
  const rectList = Array.from(selection.getRangeAt(0).getClientRects()).filter(
    (rect) => rect.width > 0 && rect.height > 0,
  );
  if (!rectList.length) return null;

  const rects: PdfAnnotationRect[] = [];
  let selectedPage: number | null = null;
  for (const clientRect of rectList) {
    const page = pageContainingRect(root, clientRect);
    if (!page) return null;
    const normalized = rectFromPageAndClientRect(page, clientRect);
    if (!normalized) continue;
    if (selectedPage !== null && normalized.page !== selectedPage) return null;
    selectedPage = normalized.page;
    rects.push(normalized);
  }
  if (!rects.length) return null;

  return {
    id,
    type: "text",
    rects,
    quote,
    comment: "",
    created_at: now,
    updated_at: now,
  };
}

export function overlayStyleForRect(rect: PdfAnnotationRect) {
  return [
    "position: absolute",
    `left: ${round(rect.x * 100)}%`,
    `top: ${round(rect.y * 100)}%`,
    `width: ${round(rect.width * 100)}%`,
    `height: ${round(rect.height * 100)}%`,
  ].join("; ");
}
