// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderPdfIntoContainer } from "./pdf-renderer";

vi.mock("pdfjs-dist/legacy/build/pdf.worker.mjs?url", () => ({
  default: "/mock-pdf-worker.mjs",
}));

const renderTask = { cancel: vi.fn(), promise: Promise.resolve() };
const destroyPdf = vi.fn();
const getViewport = vi.fn(({ scale }: { scale: number }) => ({
  width: 200 * scale,
  height: 400 * scale,
  transform: [scale, 0, 0, -scale, 0, 400 * scale],
}));
const pageRender = vi.fn(() => renderTask);
const getTextContent = vi.fn(async () => ({
  items: [
    {
      str: "Hello",
      transform: [1, 0, 0, 12, 30, 60],
    },
  ],
}));
const getPage = vi.fn(async () => ({
  getViewport,
  render: pageRender,
  getTextContent,
}));
const getDocument = vi.fn(() => ({
  promise: Promise.resolve({
    numPages: 1,
    getPage,
    destroy: destroyPdf,
  }),
}));
const pdfTransform = vi.fn(() => [1, 0, 0, 12, 30, 60]);

vi.mock("pdfjs-dist/legacy/build/pdf.mjs", () => ({
  default: {},
  GlobalWorkerOptions: { workerSrc: "" },
  getDocument,
  Util: { transform: pdfTransform },
}));

describe("renderPdfIntoContainer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      {} as CanvasRenderingContext2D,
    );
    Object.defineProperty(window, "devicePixelRatio", {
      configurable: true,
      value: 2,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  it("renders canvases with a high-DPI backing store without changing CSS layout size", async () => {
    const container = document.createElement("div");
    await renderPdfIntoContainer(container, new Uint8Array([1, 2, 3]).buffer, {
      scale: 1.5,
    });

    const page = container.querySelector<HTMLElement>(".pdf-page")!;
    const canvas = container.querySelector<HTMLCanvasElement>("canvas")!;

    expect(getViewport).toHaveBeenCalledWith({ scale: 1.5 });
    expect(page.style.width).toBe("300px");
    expect(page.style.height).toBe("600px");
    expect(canvas.style.width).toBe("300px");
    expect(canvas.style.height).toBe("600px");
    expect(canvas.width).toBe(600);
    expect(canvas.height).toBe(1200);
    expect(pageRender).toHaveBeenCalledWith(
      expect.objectContaining({
        canvas,
        canvasContext: expect.any(Object),
        transform: [2, 0, 0, 2, 0, 0],
      }),
    );
  });

  it("keeps PDF zoom scale separate from output pixel scale", async () => {
    const container = document.createElement("div");
    await renderPdfIntoContainer(container, new Uint8Array([1, 2, 3]).buffer, {
      scale: 1.25,
      outputScale: 1.75,
    });

    const canvas = container.querySelector<HTMLCanvasElement>("canvas")!;

    expect(getViewport).toHaveBeenCalledWith({ scale: 1.25 });
    expect(canvas.style.width).toBe("250px");
    expect(canvas.style.height).toBe("500px");
    expect(canvas.width).toBe(438);
    expect(canvas.height).toBe(875);
    expect(pageRender).toHaveBeenCalledWith(
      expect.objectContaining({ transform: [1.75, 0, 0, 1.75, 0, 0] }),
    );
  });

  it("clamps very high devicePixelRatio values to a bounded output scale", async () => {
    Object.defineProperty(window, "devicePixelRatio", {
      configurable: true,
      value: 5,
    });
    const container = document.createElement("div");
    await renderPdfIntoContainer(container, new Uint8Array([1, 2, 3]).buffer, {
      scale: 1,
    });

    const canvas = container.querySelector<HTMLCanvasElement>("canvas")!;
    expect(canvas.width).toBe(600);
    expect(canvas.height).toBe(1200);
    expect(pageRender).toHaveBeenCalledWith(
      expect.objectContaining({ transform: [3, 0, 0, 3, 0, 0] }),
    );
  });

  it("lays out the text layer in CSS viewport coordinates rather than output pixels", async () => {
    const container = document.createElement("div");
    await renderPdfIntoContainer(container, new Uint8Array([1, 2, 3]).buffer, {
      scale: 1,
      outputScale: 3,
    });

    const item = container.querySelector<HTMLElement>(".pdf-text-item")!;

    expect(pdfTransform).toHaveBeenCalled();
    expect(item.style.left).toBe("30px");
    expect(item.style.top).toBe("48px");
    expect(item.style.fontSize).toBe("12px");
  });
});
