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

  function deferred<T>() {
    let resolve!: (value: T | PromiseLike<T>) => void;
    const promise = new Promise<T>((next) => {
      resolve = next;
    });
    return { promise, resolve };
  }

  async function flushPromises() {
    for (let i = 0; i < 6; i += 1) await Promise.resolve();
  }

  async function waitFor(assertion: () => void | Promise<void>) {
    let lastError: unknown;
    for (let i = 0; i < 30; i += 1) {
      try {
        await assertion();
        return;
      } catch (error) {
        lastError = error;
        await flushPromises();
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
    }
    throw lastError;
  }

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

  it("notifies when the PDF document page count is known", async () => {
    getDocument.mockReturnValueOnce({
      promise: Promise.resolve({
        numPages: 7,
        getPage,
        destroy: destroyPdf,
      }),
    });
    const container = document.createElement("div");
    const onDocumentLoaded = vi.fn();

    await renderPdfIntoContainer(container, new Uint8Array([1, 2, 3]).buffer, {
      onDocumentLoaded,
    });

    expect(onDocumentLoaded).toHaveBeenCalledWith({ pageCount: 7 });
  });

  it("notifies when the first page canvas has rendered before the whole PDF finishes", async () => {
    const secondPageRender = deferred<void>();
    getDocument.mockReturnValueOnce({
      promise: Promise.resolve({
        numPages: 2,
        getPage,
        destroy: destroyPdf,
      }),
    });
    pageRender
      .mockImplementationOnce(() => ({
        cancel: vi.fn(),
        promise: Promise.resolve(),
      }))
      .mockImplementationOnce(() => ({
        cancel: vi.fn(),
        promise: secondPageRender.promise,
      }));
    const container = document.createElement("div");
    const onFirstPageRendered = vi.fn();
    let fullRenderResolved = false;

    const renderPromise = renderPdfIntoContainer(
      container,
      new Uint8Array([1, 2, 3]).buffer,
      { onFirstPageRendered },
    ).then(() => {
      fullRenderResolved = true;
    });
    try {
      await waitFor(() => {
        expect(onFirstPageRendered).toHaveBeenCalledTimes(1);
      });
      expect(container.querySelectorAll(".pdf-page")).toHaveLength(2);
      expect(fullRenderResolved).toBe(false);
    } finally {
      secondPageRender.resolve();
      await renderPromise;
    }
    expect(fullRenderResolved).toBe(true);
  });

  it("lays out all page placeholders before the first rendered page is revealed", async () => {
    const secondPageRender = deferred<void>();
    getDocument.mockReturnValueOnce({
      promise: Promise.resolve({
        numPages: 3,
        getPage,
        destroy: destroyPdf,
      }),
    });
    pageRender
      .mockImplementationOnce(() => ({
        cancel: vi.fn(),
        promise: Promise.resolve(),
      }))
      .mockImplementationOnce(() => ({
        cancel: vi.fn(),
        promise: secondPageRender.promise,
      }))
      .mockImplementationOnce(() => ({
        cancel: vi.fn(),
        promise: Promise.resolve(),
      }));
    const container = document.createElement("div");
    let pageCountAtFirstReveal = 0;

    const renderPromise = renderPdfIntoContainer(
      container,
      new Uint8Array([1, 2, 3]).buffer,
      {
        onFirstPageRendered: () => {
          pageCountAtFirstReveal =
            container.querySelectorAll(".pdf-page").length;
        },
      },
    );
    await waitFor(() => {
      expect(pageCountAtFirstReveal).toBe(3);
    });
    expect(container.querySelectorAll(".pdf-page")).toHaveLength(3);

    secondPageRender.resolve();
    await renderPromise;
  });

  it("keeps user scroll stable after first reveal because all pages are already laid out", async () => {
    getDocument.mockReturnValueOnce({
      promise: Promise.resolve({
        numPages: 3,
        getPage,
        destroy: destroyPdf,
      }),
    });
    const container = document.createElement("div");
    let scrollTopValue = 0;
    Object.defineProperty(container, "scrollTop", {
      configurable: true,
      get: () => scrollTopValue,
      set: (value) => {
        scrollTopValue = value;
      },
    });
    Object.defineProperty(container, "scrollHeight", {
      configurable: true,
      get: () => container.querySelectorAll(".pdf-page").length * 1000,
    });
    Object.defineProperty(container, "clientHeight", {
      configurable: true,
      value: 100,
    });

    await renderPdfIntoContainer(container, new Uint8Array([1, 2, 3]).buffer, {
      onFirstPageRendered: () => {
        expect(container.querySelectorAll(".pdf-page")).toHaveLength(3);
        container.scrollTop = 1450;
      },
    });

    expect(container.querySelectorAll(".pdf-page")).toHaveLength(3);
    expect(container.scrollTop).toBeCloseTo(1450, 0);
  });

  it("keeps existing rendered pages visible until the replacement layout is ready", async () => {
    const pdfLoad = deferred<{
      numPages: number;
      getPage: typeof getPage;
      destroy: typeof destroyPdf;
    }>();
    getDocument.mockReturnValueOnce({ promise: pdfLoad.promise });
    const container = document.createElement("div");
    const oldPage = document.createElement("section");
    oldPage.className = "pdf-page";
    oldPage.textContent = "old page";
    container.appendChild(oldPage);

    const renderPromise = renderPdfIntoContainer(
      container,
      new Uint8Array([1, 2, 3]).buffer,
      { scale: 1.25 },
    );

    await flushPromises();
    expect(container.textContent).toContain("old page");
    expect(container.querySelectorAll(".pdf-page")).toHaveLength(1);

    pdfLoad.resolve({ numPages: 1, getPage, destroy: destroyPdf });
    await renderPromise;
    expect(container.textContent).not.toContain("old page");
    expect(container.querySelectorAll(".pdf-page")).toHaveLength(1);
  });

  it("preserves relative scroll progress when replacing pages during zoom", async () => {
    getDocument.mockReturnValueOnce({
      promise: Promise.resolve({
        numPages: 2,
        getPage,
        destroy: destroyPdf,
      }),
    });
    const container = document.createElement("div");
    for (let pageNumber = 1; pageNumber <= 2; pageNumber += 1) {
      const oldPage = document.createElement("section");
      oldPage.className = "pdf-page";
      oldPage.style.height = "400px";
      container.appendChild(oldPage);
    }
    let scrollTopValue = 350;
    Object.defineProperty(container, "scrollTop", {
      configurable: true,
      get: () => scrollTopValue,
      set: (value) => {
        scrollTopValue = value;
      },
    });
    Object.defineProperty(container, "scrollHeight", {
      configurable: true,
      get: () =>
        Array.from(container.querySelectorAll<HTMLElement>(".pdf-page"))
          .map((page) => Number.parseFloat(page.style.height) || 0)
          .reduce((total, height) => total + height, 0),
    });
    Object.defineProperty(container, "clientHeight", {
      configurable: true,
      value: 100,
    });

    await renderPdfIntoContainer(container, new Uint8Array([1, 2, 3]).buffer, {
      scale: 2,
      outputScale: 1,
    });

    expect(container.querySelectorAll(".pdf-page")).toHaveLength(2);
    expect(container.scrollHeight).toBe(1600);
    expect(container.scrollTop).toBeCloseTo(750, 0);
  });

  it("keeps existing pages visible until replacement page content has rendered", async () => {
    const secondPageRender = deferred<void>();
    getDocument.mockReturnValueOnce({
      promise: Promise.resolve({
        numPages: 2,
        getPage,
        destroy: destroyPdf,
      }),
    });
    pageRender
      .mockImplementationOnce(() => ({
        cancel: vi.fn(),
        promise: Promise.resolve(),
      }))
      .mockImplementationOnce(() => ({
        cancel: vi.fn(),
        promise: secondPageRender.promise,
      }));
    const container = document.createElement("div");
    const oldPage = document.createElement("section");
    oldPage.className = "pdf-page";
    oldPage.textContent = "old page";
    container.appendChild(oldPage);
    let textAtFirstPageRendered = "";
    let attachedPageCountAtFirstPageRendered = 0;

    const renderPromise = renderPdfIntoContainer(
      container,
      new Uint8Array([1, 2, 3]).buffer,
      {
        onFirstPageRendered: () => {
          textAtFirstPageRendered = container.textContent ?? "";
          attachedPageCountAtFirstPageRendered =
            container.querySelectorAll(".pdf-page").length;
        },
      },
    );

    await waitFor(() => {
      expect(textAtFirstPageRendered).toContain("old page");
    });
    expect(attachedPageCountAtFirstPageRendered).toBe(1);
    expect(container.textContent).toContain("old page");

    secondPageRender.resolve();
    await renderPromise;
    expect(container.textContent).not.toContain("old page");
    expect(container.querySelectorAll(".pdf-page")).toHaveLength(2);
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

  it("treats 100% fit zoom as the largest scale that keeps the whole page visible", async () => {
    const container = document.createElement("div");
    Object.defineProperty(container, "clientWidth", {
      configurable: true,
      value: 500,
    });
    Object.defineProperty(container, "clientHeight", {
      configurable: true,
      value: 900,
    });
    container.style.padding = "16px";

    await renderPdfIntoContainer(container, new Uint8Array([1, 2, 3]).buffer, {
      scale: 1,
      outputScale: 1,
      fitToContainer: true,
    });

    const page = container.querySelector<HTMLElement>(".pdf-page")!;
    expect(getViewport).toHaveBeenCalledWith({ scale: 1 });
    expect(getViewport).toHaveBeenCalledWith({ scale: 2.17 });
    expect(page.style.width).toBe("434px");
    expect(page.style.height).toBe("868px");
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
