// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { apiClient } from "$lib/api/client.js";
import PdfViewer from "./PdfViewer.svelte";
import { renderPdfIntoContainer } from "./pdf-renderer";
import type { PdfAnnotationDocument } from "./annotations";

vi.mock("$lib/api/client.js", () => ({
  apiClient: vi.fn(),
}));

vi.mock("./pdf-renderer", () => ({
  renderPdfIntoContainer: vi.fn(),
}));

const pdfBytes = new Uint8Array([37, 80, 68, 70]).buffer;
const emptyDoc: PdfAnnotationDocument = {
  version: 1,
  source_path: "reports/report.pdf",
  annotations: [],
};

function domRect(rect: Partial<DOMRect>): DOMRect {
  const left = rect.left ?? rect.x ?? 0;
  const top = rect.top ?? rect.y ?? 0;
  const width = rect.width ?? 0;
  const height = rect.height ?? 0;
  return {
    x: left,
    y: top,
    left,
    top,
    right: rect.right ?? left + width,
    bottom: rect.bottom ?? top + height,
    width,
    height,
    toJSON: () => ({}),
  } as DOMRect;
}

function setScrollMetrics(
  element: HTMLElement,
  metrics: { scrollTop: number; scrollHeight: number; clientHeight: number },
) {
  Object.defineProperty(element, "scrollTop", {
    configurable: true,
    writable: true,
    value: metrics.scrollTop,
  });
  Object.defineProperty(element, "scrollHeight", {
    configurable: true,
    value: metrics.scrollHeight,
  });
  Object.defineProperty(element, "clientHeight", {
    configurable: true,
    value: metrics.clientHeight,
  });
}

function installOnePage(
  container: HTMLElement,
  pageNumber = 1,
  rect: Partial<DOMRect> = {
    left: 100,
    top: 50,
    width: 200,
    height: 400,
  },
) {
  const page = document.createElement("section");
  page.className = "pdf-page";
  page.dataset.pageNumber = String(pageNumber);
  page.getBoundingClientRect = vi.fn(() => domRect(rect));
  container.appendChild(page);
  return page;
}

describe("PdfViewer", () => {
  beforeEach(() => {
    vi.mocked(renderPdfIntoContainer).mockImplementation(async (container) => {
      installOnePage(container);
      return () => undefined;
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.mocked(apiClient).mockReset();
    vi.mocked(renderPdfIntoContainer).mockReset();
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  function deferred<T>() {
    let resolve!: (value: T | PromiseLike<T>) => void;
    const promise = new Promise<T>((next) => {
      resolve = next;
    });
    return { promise, resolve };
  }

  async function waitFor(assertion: () => void | Promise<void>) {
    let lastError: unknown;
    for (let i = 0; i < 30; i += 1) {
      try {
        await assertion();
        return;
      } catch (error) {
        lastError = error;
        await Promise.resolve();
        await new Promise((resolve) => setTimeout(resolve, 0));
        await tick();
      }
    }
    throw lastError;
  }

  function mockApi(annotationDoc = emptyDoc) {
    const toV2 = (doc: typeof emptyDoc) => ({
      version: 2,
      source_key: `data:${doc.source_path}`,
      source: { kind: "data", path: doc.source_path },
      annotations: doc.annotations.map((annotation) => {
        const anchor: Record<string, unknown> = {
          kind: annotation.type === "text" ? "pdf_text" : "pdf_rects",
          rects: annotation.rects,
        };
        if (annotation.type === "text" && "quote" in annotation) {
          anchor.quote = annotation.quote;
        }
        return {
          id: annotation.id,
          kind: annotation.type,
          anchor,
          comment: annotation.comment,
          created_at: annotation.created_at,
          updated_at: annotation.updated_at,
        };
      }),
    });
    vi.mocked(apiClient).mockImplementation(async (url, options = {}) => {
      const method = options.method ?? "GET";
      if (String(url).includes("/annotations/data/") && method === "GET") {
        return new Response(JSON.stringify(toV2(annotationDoc)), {
          status: 200,
        });
      }
      if (String(url).includes("/annotations/data/") && method === "PUT") {
        return new Response(String(options.body), { status: 200 });
      }
      return new Response(pdfBytes.slice(0), { status: 200 });
    });
  }

  it("fetches authenticated PDF bytes and sends an ArrayBuffer to the renderer", async () => {
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
    });

    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/taeho/data/reports/report.pdf",
      expect.objectContaining({ method: "GET" }),
    );
    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/taeho/annotations/data/reports/report.pdf",
      expect.objectContaining({ method: "GET" }),
    );
    const [container, buffer, options] = vi.mocked(renderPdfIntoContainer).mock
      .calls[0];
    expect(container).toBeInstanceOf(HTMLDivElement);
    expect(buffer).toBeInstanceOf(ArrayBuffer);
    expect(options).toMatchObject({ scale: 1, fitToContainer: true });
    expect(Array.from(new Uint8Array(buffer as ArrayBuffer))).toEqual([
      37, 80, 68, 70,
    ]);
    expect(target.querySelector('[data-testid="pdf-preview"]')).not.toBeNull();

    unmount(component);
  });

  it("shows the first rendered PDF page before the full document render resolves", async () => {
    const renderDeferred = deferred<() => void>();
    vi.mocked(renderPdfIntoContainer).mockImplementation(
      async (container, _buffer, options) => {
        installOnePage(container);
        options?.onFirstPageRendered?.();
        return renderDeferred.promise;
      },
    );
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
      expect(target.querySelector(".pdf-page")).not.toBeNull();
      expect(target.querySelector('[data-testid="pdf-loading"]')).toBeNull();
      expect(
        target.querySelector('[data-testid="pdf-pages"]')?.classList,
      ).not.toContain("initial-rendering");
    });

    expect(
      target.querySelector<HTMLButtonElement>('[data-testid="pdf-zoom-in"]')
        ?.disabled,
    ).toBe(false);
    expect(
      vi
        .mocked(apiClient)
        .mock.calls.find(([url]) => String(url).includes("/annotations/data/")),
    ).toBeUndefined();

    renderDeferred.resolve(() => undefined);
    await waitFor(() => {
      expect(
        vi
          .mocked(apiClient)
          .mock.calls.find(([url]) =>
            String(url).includes("/annotations/data/"),
          ),
      ).toBeDefined();
    });

    unmount(component);
  });

  it("shows a transient right-side scroll overlay with the current PDF page number", async () => {
    vi.mocked(renderPdfIntoContainer).mockImplementation(
      async (container, _buffer, options) => {
        setScrollMetrics(container, {
          scrollTop: 500,
          scrollHeight: 1500,
          clientHeight: 500,
        });
        container.getBoundingClientRect = vi.fn(() =>
          domRect({ left: 0, top: 100, width: 900, height: 500 }),
        );
        options?.onDocumentLoaded?.({ pageCount: 3 });
        installOnePage(container, 1, {
          left: 100,
          top: -450,
          width: 600,
          height: 400,
        });
        installOnePage(container, 2, {
          left: 100,
          top: 150,
          width: 600,
          height: 400,
        });
        installOnePage(container, 3, {
          left: 100,
          top: 750,
          width: 600,
          height: 400,
        });
        options?.onFirstPageRendered?.();
        return () => undefined;
      },
    );
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(target.querySelector('[data-testid="pdf-pages"]')).not.toBeNull();
      expect(target.querySelector('[data-testid="pdf-loading"]')).toBeNull();
    });
    await tick();
    await tick();
    const pages = target.querySelector<HTMLElement>(
      '[data-testid="pdf-pages"]',
    )!;
    await waitFor(() => {
      pages.dispatchEvent(new Event("scroll"));
      const overlay = target.querySelector(
        '[data-testid="pdf-scroll-position-overlay"]',
      );
      expect(overlay).not.toBeNull();
      expect(overlay?.textContent).toContain("50% · Page 2 / 3");
    });

    await new Promise((resolve) => setTimeout(resolve, 950));
    await tick();
    expect(
      target.querySelector('[data-testid="pdf-scroll-position-overlay"]'),
    ).toBeNull();

    unmount(component);
  });

  it("does not restart an active PDF render for resize events", async () => {
    const renderDeferred = deferred<() => void>();
    let firstSignal: AbortSignal | undefined;
    vi.mocked(renderPdfIntoContainer).mockImplementation(
      async (container, _buffer, options) => {
        firstSignal = options?.signal;
        installOnePage(container);
        return renderDeferred.promise;
      },
    );
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
    });
    vi.useFakeTimers();

    window.dispatchEvent(new Event("resize"));
    await vi.advanceTimersByTimeAsync(120);

    expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
    expect(firstSignal?.aborted).toBe(false);

    renderDeferred.resolve(() => undefined);
    await vi.runOnlyPendingTimersAsync();
    vi.useRealTimers();
    await tick();

    unmount(component);
  });

  it("does not allow zoom controls to uncover the initial PDF render", async () => {
    const renderDeferred = deferred<() => void>();
    let markFirstPageRendered: (() => void) | undefined;
    vi.mocked(renderPdfIntoContainer).mockImplementation(
      async (container, _buffer, options) => {
        installOnePage(container);
        markFirstPageRendered = options?.onFirstPageRendered;
        return renderDeferred.promise;
      },
    );
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
      expect(
        target.querySelector('[data-testid="pdf-loading"]'),
      ).not.toBeNull();
    });
    const zoomIn = target.querySelector<HTMLButtonElement>(
      '[data-testid="pdf-zoom-in"]',
    )!;
    expect(zoomIn.disabled).toBe(true);

    markFirstPageRendered?.();
    await waitFor(() => {
      expect(target.querySelector('[data-testid="pdf-loading"]')).toBeNull();
      expect(zoomIn.disabled).toBe(false);
    });

    zoomIn.click();
    await tick();
    expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
    expect(target.querySelector(".pdf-page")).not.toBeNull();

    renderDeferred.resolve(() => undefined);
    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(2);
    });

    unmount(component);
  });

  it("still renders the PDF when annotation loading fails", async () => {
    vi.mocked(apiClient).mockImplementation(async (url, options = {}) => {
      const method = options.method ?? "GET";
      if (String(url).includes("/annotations/data/") && method === "GET") {
        return new Response("annotation service unavailable", { status: 503 });
      }
      return new Response(pdfBytes.slice(0), { status: 200 });
    });
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
      expect(target.querySelector(".pdf-page")).not.toBeNull();
    });
    await waitFor(() => {
      expect(target.querySelector(".notice.error")?.textContent).toContain(
        "GET PDF annotations → 503",
      );
    });

    unmount(component);
  });

  it("zooms the rendered PDF without re-fetching bytes and uses fresh buffers", async () => {
    const firstCleanup = vi.fn();
    const secondCleanup = vi.fn();
    vi.mocked(renderPdfIntoContainer).mockImplementation(async (container) => {
      installOnePage(container);
      return vi.mocked(renderPdfIntoContainer).mock.calls.length === 1
        ? firstCleanup
        : secondCleanup;
    });
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
    });

    expect(
      target.querySelector('[data-testid="pdf-zoom-label"]')?.textContent,
    ).toBe("100%");
    target
      .querySelector<HTMLButtonElement>('[data-testid="pdf-zoom-in"]')
      ?.click();

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(2);
    });

    expect(firstCleanup).toHaveBeenCalledTimes(1);
    expect(secondCleanup).not.toHaveBeenCalled();
    expect(
      target.querySelector('[data-testid="pdf-zoom-label"]')?.textContent,
    ).toBe("125%");
    expect(vi.mocked(renderPdfIntoContainer).mock.calls[1][2]).toMatchObject({
      scale: 1.25,
      fitToContainer: true,
    });
    expect(vi.mocked(renderPdfIntoContainer).mock.calls[0][1]).not.toBe(
      vi.mocked(renderPdfIntoContainer).mock.calls[1][1],
    );
    const pdfFetches = vi
      .mocked(apiClient)
      .mock.calls.filter(
        ([url, options]) =>
          String(url).includes("/api/v1/vault/taeho/data/reports/report.pdf") &&
          options?.method === "GET",
      );
    expect(pdfFetches).toHaveLength(1);

    unmount(component);
    expect(secondCleanup).toHaveBeenCalledTimes(1);
  });

  it("keeps the previous rendered PDF visible while a zoom render is pending", async () => {
    const secondRender = deferred<() => void>();
    let oldPage: HTMLElement | null = null;
    const firstCleanup = vi.fn(() => oldPage?.remove());
    const secondCleanup = vi.fn();
    vi.mocked(renderPdfIntoContainer).mockImplementation(async (container) => {
      if (vi.mocked(renderPdfIntoContainer).mock.calls.length === 1) {
        oldPage = installOnePage(container);
        return firstCleanup;
      }
      return secondRender.promise;
    });
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
      expect(target.querySelector(".pdf-page")).not.toBeNull();
    });

    target
      .querySelector<HTMLButtonElement>('[data-testid="pdf-zoom-in"]')
      ?.click();
    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(2);
    });

    expect(firstCleanup).not.toHaveBeenCalled();
    expect(target.querySelector(".pdf-page")).toBe(oldPage);

    secondRender.resolve(secondCleanup);
    await waitFor(() => {
      expect(firstCleanup).toHaveBeenCalledTimes(1);
    });

    unmount(component);
    expect(secondCleanup).toHaveBeenCalledTimes(1);
  });

  it("queues zoom until the visible initial render finishes instead of aborting it", async () => {
    const firstRender = deferred<() => void>();
    const secondRender = deferred<() => void>();
    let oldPage: HTMLElement | null = null;
    const firstCleanup = vi.fn(() => oldPage?.remove());
    const secondCleanup = vi.fn();
    vi.mocked(renderPdfIntoContainer).mockImplementation(
      async (container, _buffer, options) => {
        if (vi.mocked(renderPdfIntoContainer).mock.calls.length === 1) {
          oldPage = installOnePage(container);
          options?.onFirstPageRendered?.();
          return firstRender.promise;
        }
        installOnePage(container, 2);
        return secondRender.promise;
      },
    );
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
      expect(target.querySelector(".pdf-page")).toBe(oldPage);
      expect(
        target.querySelector<HTMLButtonElement>('[data-testid="pdf-zoom-in"]')
          ?.disabled,
      ).toBe(false);
    });

    target
      .querySelector<HTMLButtonElement>('[data-testid="pdf-zoom-in"]')
      ?.click();
    await tick();

    expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
    expect(firstCleanup).not.toHaveBeenCalled();
    expect(target.querySelector(".pdf-page")).toBe(oldPage);
    expect(
      target.querySelector('[data-testid="pdf-zoom-label"]')?.textContent,
    ).toBe("125%");

    firstRender.resolve(firstCleanup);
    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(2);
    });
    expect(firstCleanup).not.toHaveBeenCalled();
    expect(target.querySelector(".pdf-page")).toBe(oldPage);

    secondRender.resolve(secondCleanup);
    await waitFor(() => {
      expect(firstCleanup).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-zoom-label"]')?.textContent,
      ).toBe("125%");
    });

    unmount(component);
    expect(secondCleanup).toHaveBeenCalledTimes(1);
  });

  it("clamps zoom controls and can reset to the default scale", async () => {
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
    });
    const zoomOut = target.querySelector<HTMLButtonElement>(
      '[data-testid="pdf-zoom-out"]',
    )!;
    const zoomIn = target.querySelector<HTMLButtonElement>(
      '[data-testid="pdf-zoom-in"]',
    )!;
    const reset = target.querySelector<HTMLButtonElement>(
      '[data-testid="pdf-zoom-reset"]',
    )!;
    expect(reset.getAttribute("aria-label")).toBe("Reset zoom");

    for (let i = 0; i < 10; i += 1) zoomOut.click();
    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-zoom-label"]')?.textContent,
      ).toBe("75%");
    });
    expect(zoomOut.disabled).toBe(true);

    for (let i = 0; i < 20; i += 1) zoomIn.click();
    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-zoom-label"]')?.textContent,
      ).toBe("300%");
    });
    expect(zoomIn.disabled).toBe(true);

    reset.click();
    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-zoom-label"]')?.textContent,
      ).toBe("100%");
    });

    unmount(component);
  });

  it("renders persisted annotation overlays after reload", async () => {
    mockApi({
      version: 1,
      source_path: "reports/report.pdf",
      annotations: [
        {
          id: "area-1",
          type: "area",
          rects: [{ page: 1, x: 0.1, y: 0.2, width: 0.3, height: 0.4 }],
          comment: "",
          created_at: "2026-06-29T08:00:00Z",
          updated_at: "2026-06-29T08:00:00Z",
        },
      ],
    });
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(target.querySelectorAll(".pdf-annotation-overlay")).toHaveLength(
        1,
      );
    });
    expect(
      target
        .querySelector(".pdf-annotation-overlay")
        ?.getAttribute("data-annotation-id"),
    ).toBe("area-1");

    unmount(component);
  });
  it("opens a popup for a persisted annotation and saves an edited comment", async () => {
    mockApi({
      version: 1,
      source_path: "reports/report.pdf",
      annotations: [
        {
          id: "area-edit-1",
          type: "area",
          rects: [{ page: 1, x: 0.1, y: 0.2, width: 0.3, height: 0.4 }],
          comment: "old comment",
          created_at: "2026-06-29T08:00:00Z",
          updated_at: "2026-06-29T08:00:00Z",
        },
      ],
    });
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(target.querySelector(".pdf-annotation-overlay")).not.toBeNull();
    });
    target
      .querySelector<HTMLElement>(".pdf-annotation-overlay")
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-annotation-menu"]'),
      ).not.toBeNull();
    });
    const textarea = target.querySelector<HTMLTextAreaElement>(
      '[data-testid="pdf-annotation-comment"]',
    )!;
    expect(textarea.value).toBe("old comment");
    textarea.value = "updated comment";
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    target
      .querySelector<HTMLButtonElement>('[data-testid="pdf-annotation-save"]')
      ?.click();

    await waitFor(() => {
      const putCall = vi
        .mocked(apiClient)
        .mock.calls.find(
          ([url, options]) =>
            String(url).includes("/annotations/data/") &&
            options?.method === "PUT",
        );
      expect(putCall).toBeDefined();
      const saved = JSON.parse(String(putCall?.[1]?.body));
      expect(saved.annotations[0]).toMatchObject({
        id: "area-edit-1",
        comment: "updated comment",
        created_at: "2026-06-29T08:00:00Z",
      });
      expect(saved.annotations[0].updated_at).not.toBe("2026-06-29T08:00:00Z");
    });

    unmount(component);
  });

  it("keeps an open annotation popup and draft intact during viewport resize", async () => {
    mockApi({
      version: 1,
      source_path: "reports/report.pdf",
      annotations: [
        {
          id: "area-resize-1",
          type: "area",
          rects: [{ page: 1, x: 0.1, y: 0.2, width: 0.3, height: 0.4 }],
          comment: "before resize",
          created_at: "2026-06-29T08:00:00Z",
          updated_at: "2026-06-29T08:00:00Z",
        },
      ],
    });
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(target.querySelector(".pdf-annotation-overlay")).not.toBeNull();
    });
    target
      .querySelector<HTMLElement>(".pdf-annotation-overlay")
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-annotation-menu"]'),
      ).not.toBeNull();
    });
    const textarea = target.querySelector<HTMLTextAreaElement>(
      '[data-testid="pdf-annotation-comment"]',
    )!;
    textarea.value = "draft survives resize";
    textarea.dispatchEvent(new Event("input", { bubbles: true }));

    window.dispatchEvent(new Event("resize"));
    await new Promise((resolve) => setTimeout(resolve, 120));
    await tick();

    expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
    expect(
      target.querySelector('[data-testid="pdf-annotation-menu"]'),
    ).not.toBeNull();
    expect(
      target.querySelector<HTMLTextAreaElement>(
        '[data-testid="pdf-annotation-comment"]',
      )?.value,
    ).toBe("draft survives resize");

    unmount(component);
  });

  it("deletes a persisted annotation from its popup", async () => {
    mockApi({
      version: 1,
      source_path: "reports/report.pdf",
      annotations: [
        {
          id: "area-delete-1",
          type: "area",
          rects: [{ page: 1, x: 0.1, y: 0.2, width: 0.3, height: 0.4 }],
          comment: "remove me",
          created_at: "2026-06-29T08:00:00Z",
          updated_at: "2026-06-29T08:00:00Z",
        },
      ],
    });
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(target.querySelector(".pdf-annotation-overlay")).not.toBeNull();
    });
    target
      .querySelector<HTMLElement>(".pdf-annotation-overlay")
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-annotation-delete"]'),
      ).not.toBeNull();
    });
    target
      .querySelector<HTMLButtonElement>('[data-testid="pdf-annotation-delete"]')
      ?.click();

    await waitFor(() => {
      const putCall = vi
        .mocked(apiClient)
        .mock.calls.find(
          ([url, options]) =>
            String(url).includes("/annotations/data/") &&
            options?.method === "PUT",
        );
      expect(putCall).toBeDefined();
      const saved = JSON.parse(String(putCall?.[1]?.body));
      expect(saved.annotations).toEqual([]);
    });

    unmount(component);
  });

  it("repaints persisted annotation overlays after zooming", async () => {
    vi.mocked(renderPdfIntoContainer).mockImplementation(async (container) => {
      const page = installOnePage(container);
      return () => page.remove();
    });
    mockApi({
      version: 1,
      source_path: "reports/report.pdf",
      annotations: [
        {
          id: "area-zoom-1",
          type: "area",
          rects: [{ page: 1, x: 0.1, y: 0.2, width: 0.3, height: 0.4 }],
          comment: "",
          created_at: "2026-06-29T08:00:00Z",
          updated_at: "2026-06-29T08:00:00Z",
        },
      ],
    });
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(target.querySelectorAll(".pdf-annotation-overlay")).toHaveLength(
        1,
      );
    });
    target
      .querySelector<HTMLButtonElement>('[data-testid="pdf-zoom-in"]')
      ?.click();

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(2);
      expect(target.querySelectorAll(".pdf-page")).toHaveLength(1);
      expect(target.querySelectorAll(".pdf-annotation-overlay")).toHaveLength(
        1,
      );
      expect(
        target
          .querySelector(".pdf-annotation-overlay")
          ?.getAttribute("data-annotation-id"),
      ).toBe("area-zoom-1");
    });

    unmount(component);
  });

  it("shows annotations button count and document annotation cards", async () => {
    mockApi({
      version: 1,
      source_path: "reports/report.pdf",
      annotations: [
        {
          id: "text-card-1",
          type: "text",
          rects: [{ page: 1, x: 0.1, y: 0.2, width: 0.3, height: 0.05 }],
          quote: "quoted source text",
          comment: "human note",
          created_at: "2026-06-29T08:00:00Z",
          updated_at: "2026-06-29T09:00:00Z",
        },
        {
          id: "area-card-1",
          type: "area",
          rects: [{ page: 1, x: 0.2, y: 0.3, width: 0.2, height: 0.2 }],
          comment: "legacy area note",
          created_at: "2026-06-29T10:00:00Z",
          updated_at: "2026-06-29T10:00:00Z",
        },
      ],
    });
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-annotations-toggle"]'),
      ).not.toBeNull();
      expect(
        target.querySelector('[data-testid="pdf-annotations-toggle"]')
          ?.textContent,
      ).toContain("Annotations (2)");
    });
    expect(
      target.querySelector('[data-testid="area-annotation-mode"]'),
    ).toBeNull();
    expect(target.querySelector('[data-testid="text-annotation"]')).toBeNull();

    target
      .querySelector<HTMLButtonElement>(
        '[data-testid="pdf-annotations-toggle"]',
      )
      ?.click();

    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-annotations-panel"]'),
      ).not.toBeNull();
      expect(
        target.querySelectorAll('[data-testid="pdf-annotation-card"]'),
      ).toHaveLength(2);
    });
    expect(
      target.querySelector('[data-testid="pdf-annotations-panel"]')
        ?.textContent,
    ).toContain("quoted source text");
    expect(
      target.querySelector('[data-testid="pdf-annotations-panel"]')
        ?.textContent,
    ).toContain("human note");
    expect(
      target.querySelector('[data-testid="pdf-annotations-panel"]')
        ?.textContent,
    ).toContain("legacy area note");
    expect(
      target.querySelector('[data-testid="pdf-annotations-panel"]')
        ?.textContent,
    ).toContain("Page 1");

    unmount(component);
  });

  it("shows an empty annotation panel state when the document has no annotations", async () => {
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-annotations-toggle"]')
          ?.textContent,
      ).toContain("Annotations (0)");
    });
    target
      .querySelector<HTMLButtonElement>(
        '[data-testid="pdf-annotations-toggle"]',
      )
      ?.click();

    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-annotations-empty"]')
          ?.textContent,
      ).toContain("No annotations yet");
    });

    unmount(component);
  });

  it("keeps the PDF stable when resize fires with the annotations panel open", async () => {
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
    });
    target
      .querySelector<HTMLButtonElement>(
        '[data-testid="pdf-annotations-toggle"]',
      )
      ?.click();
    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-annotations-panel"]'),
      ).not.toBeNull();
    });

    window.dispatchEvent(new Event("resize"));
    await new Promise((resolve) => setTimeout(resolve, 120));
    await tick();

    expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
    expect(
      target.querySelector('[data-testid="pdf-annotations-panel"]'),
    ).not.toBeNull();
    expect(
      target
        .querySelector<HTMLButtonElement>(
          '[data-testid="pdf-annotations-toggle"]',
        )
        ?.classList.contains("active"),
    ).toBe(true);

    unmount(component);
  });

  it("ignores ResizeObserver churn when the PDF container size is unchanged", async () => {
    let resizeObserverCallback:
      | ((
          entries: Array<{ contentRect: { width: number; height: number } }>,
        ) => void)
      | undefined;
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(
          callback: (
            entries: Array<{ contentRect: { width: number; height: number } }>,
          ) => void,
        ) {
          resizeObserverCallback = callback;
        }
        observe = vi.fn();
        disconnect = vi.fn();
      },
    );
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    try {
      await waitFor(() => {
        expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
      });
      vi.useFakeTimers();
      const pages = target.querySelector<HTMLElement>(
        '[data-testid="pdf-pages"]',
      )!;
      setScrollMetrics(pages, {
        scrollTop: 640,
        scrollHeight: 1800,
        clientHeight: 600,
      });

      resizeObserverCallback?.([
        { contentRect: { width: 900, height: 600 } },
        { contentRect: { width: 900, height: 600 } },
      ]);
      await vi.advanceTimersByTimeAsync(120);
      await tick();

      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
      expect(pages.scrollTop).toBe(640);
    } finally {
      unmount(component);
    }
  });

  it("cancels a pending resize render when opening the annotations panel", async () => {
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
    });
    window.dispatchEvent(new Event("resize"));
    target
      .querySelector<HTMLButtonElement>(
        '[data-testid="pdf-annotations-toggle"]',
      )
      ?.click();
    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-annotations-panel"]'),
      ).not.toBeNull();
    });

    await new Promise((resolve) => setTimeout(resolve, 120));
    await tick();

    expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);

    unmount(component);
  });

  it("shows a floating Annotate button for selected PDF text before opening the draft popup", async () => {
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(target.querySelector(".pdf-page")).not.toBeNull();
    });
    vi.spyOn(window, "getSelection").mockReturnValue({
      toString: () => "draft selected words",
      rangeCount: 1,
      isCollapsed: false,
      getRangeAt: () => ({
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
      }),
    } as unknown as Selection);

    document.dispatchEvent(new Event("selectionchange"));
    target
      .querySelector<HTMLElement>(".pdf-page")
      ?.dispatchEvent(new MouseEvent("pointerup", { bubbles: true }));
    document.dispatchEvent(new Event("selectionchange"));

    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="floating-text-annotation"]'),
      ).not.toBeNull();
      expect(
        target.querySelector('[data-testid="pdf-annotation-menu"]'),
      ).toBeNull();
    });
    expect(
      vi
        .mocked(apiClient)
        .mock.calls.find(
          ([url, options]) =>
            String(url).includes("/annotations/data/") &&
            options?.method === "PUT",
        ),
    ).toBeUndefined();

    target
      .querySelector<HTMLButtonElement>(
        '[data-testid="floating-text-annotation"]',
      )
      ?.click();

    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-annotation-menu"]'),
      ).not.toBeNull();
    });
    target
      .querySelector<HTMLButtonElement>('[data-testid="pdf-annotation-save"]')
      ?.click();

    await waitFor(() => {
      const putCalls = vi
        .mocked(apiClient)
        .mock.calls.filter(
          ([url, options]) =>
            String(url).includes("/annotations/data/") &&
            options?.method === "PUT",
        );
      expect(putCalls).toHaveLength(1);
      const saved = JSON.parse(String(putCalls[0]?.[1]?.body));
      expect(saved.annotations[0]).toMatchObject({
        kind: "text",
        anchor: {
          kind: "pdf_text",
          quote: "draft selected words",
          rects: [{ page: 1, x: 0.1, y: 0.1, width: 0.2, height: 0.05 }],
        },
      });
    });

    unmount(component);
  });

  it("cancels a new text annotation draft without saving", async () => {
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(target.querySelector(".pdf-page")).not.toBeNull();
    });
    vi.spyOn(window, "getSelection").mockReturnValue({
      toString: () => "discard this draft",
      rangeCount: 1,
      isCollapsed: false,
      getRangeAt: () => ({
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
      }),
    } as unknown as Selection);

    target
      .querySelector<HTMLElement>(".pdf-page")
      ?.dispatchEvent(new MouseEvent("pointerup", { bubbles: true }));
    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="floating-text-annotation"]'),
      ).not.toBeNull();
    });
    target
      .querySelector<HTMLButtonElement>(
        '[data-testid="floating-text-annotation"]',
      )
      ?.click();
    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-annotation-menu"]'),
      ).not.toBeNull();
    });
    target
      .querySelector<HTMLButtonElement>('[data-testid="pdf-annotation-cancel"]')
      ?.click();

    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-annotation-menu"]'),
      ).toBeNull();
    });
    expect(
      vi
        .mocked(apiClient)
        .mock.calls.find(
          ([url, options]) =>
            String(url).includes("/annotations/data/") &&
            options?.method === "PUT",
        ),
    ).toBeUndefined();

    unmount(component);
  });

  it("edits and deletes persisted annotations from document annotation cards", async () => {
    mockApi({
      version: 1,
      source_path: "reports/report.pdf",
      annotations: [
        {
          id: "text-panel-1",
          type: "text",
          rects: [{ page: 1, x: 0.1, y: 0.2, width: 0.3, height: 0.05 }],
          quote: "panel quote",
          comment: "panel old comment",
          created_at: "2026-06-29T08:00:00Z",
          updated_at: "2026-06-29T08:00:00Z",
        },
      ],
    });
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-annotations-toggle"]'),
      ).not.toBeNull();
    });
    target
      .querySelector<HTMLButtonElement>(
        '[data-testid="pdf-annotations-toggle"]',
      )
      ?.click();
    await waitFor(() => {
      expect(
        target.querySelector('[data-testid="pdf-annotation-card-edit"]'),
      ).not.toBeNull();
    });
    target
      .querySelector<HTMLButtonElement>(
        '[data-testid="pdf-annotation-card-edit"]',
      )
      ?.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));

    await waitFor(() => {
      expect(
        target.querySelector<HTMLTextAreaElement>(
          '[data-testid="pdf-annotation-comment"]',
        )?.value,
      ).toBe("panel old comment");
    });
    const textarea = target.querySelector<HTMLTextAreaElement>(
      '[data-testid="pdf-annotation-comment"]',
    )!;
    textarea.value = "panel updated comment";
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    target
      .querySelector<HTMLButtonElement>('[data-testid="pdf-annotation-save"]')
      ?.click();

    await waitFor(() => {
      const putCall = vi
        .mocked(apiClient)
        .mock.calls.find(
          ([url, options]) =>
            String(url).includes("/annotations/data/") &&
            options?.method === "PUT" &&
            String(options.body).includes("panel updated comment"),
        );
      expect(putCall).toBeDefined();
    });

    target
      .querySelector<HTMLButtonElement>(
        '[data-testid="pdf-annotation-card-delete"]',
      )
      ?.click();

    await waitFor(() => {
      const putCall = vi.mocked(apiClient).mock.calls.find(([url, options]) => {
        if (
          !String(url).includes("/annotations/data/") ||
          options?.method !== "PUT"
        )
          return false;
        const saved = JSON.parse(String(options.body));
        return (
          Array.isArray(saved.annotations) && saved.annotations.length === 0
        );
      });
      expect(putCall).toBeDefined();
    });

    unmount(component);
  });

  it("does not create area annotations from page drag now that area mode is removed", async () => {
    mockApi();
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "reports/report.pdf" },
    });

    await waitFor(() => {
      expect(target.querySelector(".pdf-page")).not.toBeNull();
    });
    const page = target.querySelector<HTMLElement>(".pdf-page")!;
    page.dispatchEvent(
      new MouseEvent("pointerdown", {
        bubbles: true,
        clientX: 120,
        clientY: 90,
      }),
    );
    page.dispatchEvent(
      new MouseEvent("pointerup", {
        bubbles: true,
        clientX: 180,
        clientY: 210,
      }),
    );
    await tick();

    expect(
      vi
        .mocked(apiClient)
        .mock.calls.find(
          ([url, options]) =>
            String(url).includes("/annotations/data/") &&
            options?.method === "PUT",
        ),
    ).toBeUndefined();

    unmount(component);
  });

  it("shows an error when the PDF fetch fails", async () => {
    vi.mocked(apiClient).mockResolvedValue(
      new Response("nope", { status: 404 }),
    );
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(PdfViewer, {
      target,
      props: { vault: "taeho", path: "missing.pdf" },
    });

    await waitFor(() => {
      expect(target.querySelector('[role="alert"]')?.textContent).toContain(
        "GET PDF → 404",
      );
    });
    expect(renderPdfIntoContainer).not.toHaveBeenCalled();

    unmount(component);
  });
});
