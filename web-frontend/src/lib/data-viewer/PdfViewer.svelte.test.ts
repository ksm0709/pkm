// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { apiClient } from "$lib/api/client.js";
import PdfViewer from "./PdfViewer.svelte";
import { renderPdfIntoContainer } from "./pdf-renderer";

vi.mock("$lib/api/client.js", () => ({
  apiClient: vi.fn(),
}));

vi.mock("./pdf-renderer", () => ({
  renderPdfIntoContainer: vi.fn(),
}));

const pdfBytes = new Uint8Array([37, 80, 68, 70]).buffer;
const emptyDoc = {
  version: 1,
  source_path: "reports/report.pdf",
  annotations: [],
};

function installOnePage(container: HTMLElement) {
  const page = document.createElement("section");
  page.className = "pdf-page";
  page.dataset.pageNumber = "1";
  page.getBoundingClientRect = vi.fn(
    () =>
      ({
        x: 100,
        y: 50,
        left: 100,
        top: 50,
        right: 300,
        bottom: 450,
        width: 200,
        height: 400,
        toJSON: () => ({}),
      }) as DOMRect,
  );
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
    vi.mocked(apiClient).mockReset();
    vi.mocked(renderPdfIntoContainer).mockReset();
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

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
    vi.mocked(apiClient).mockImplementation(async (url, options = {}) => {
      const method = options.method ?? "GET";
      if (String(url).includes("/data-annotations/") && method === "GET") {
        return new Response(JSON.stringify(annotationDoc), { status: 200 });
      }
      if (String(url).includes("/data-annotations/") && method === "PUT") {
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
      "/api/v1/vault/taeho/data-annotations/reports/report.pdf",
      expect.objectContaining({ method: "GET" }),
    );
    const [container, buffer] = vi.mocked(renderPdfIntoContainer).mock.calls[0];
    expect(container).toBeInstanceOf(HTMLDivElement);
    expect(buffer).toBeInstanceOf(ArrayBuffer);
    expect(Array.from(new Uint8Array(buffer as ArrayBuffer))).toEqual([
      37, 80, 68, 70,
    ]);
    expect(target.querySelector('[data-testid="pdf-preview"]')).not.toBeNull();

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

  it("creates and saves an area annotation from a page drag", async () => {
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
    target
      .querySelector<HTMLButtonElement>('[data-testid="area-annotation-mode"]')
      ?.click();
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

    await waitFor(() => {
      expect(
        vi
          .mocked(apiClient)
          .mock.calls.find(
            ([url, options]) =>
              String(url).includes("/data-annotations/") &&
              options?.method === "PUT",
          ),
      ).toBeDefined();
    });
    const putCall = vi
      .mocked(apiClient)
      .mock.calls.find(
        ([url, options]) =>
          String(url).includes("/data-annotations/") &&
          options?.method === "PUT",
      );
    const saved = JSON.parse(String(putCall?.[1]?.body));
    expect(saved.annotations[0]).toMatchObject({
      type: "area",
      rects: [{ page: 1, x: 0.1, y: 0.1, width: 0.3, height: 0.3 }],
    });

    unmount(component);
  });

  it("creates and saves a same-page text annotation from browser selection", async () => {
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
      toString: () => "selected words",
      rangeCount: 1,
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
      .querySelector<HTMLButtonElement>('[data-testid="text-annotation"]')
      ?.click();

    await waitFor(() => {
      const putCall = vi
        .mocked(apiClient)
        .mock.calls.find(
          ([url, options]) =>
            String(url).includes("/data-annotations/") &&
            options?.method === "PUT",
        );
      expect(putCall).toBeDefined();
      const saved = JSON.parse(String(putCall?.[1]?.body));
      expect(saved.annotations[0]).toMatchObject({
        type: "text",
        quote: "selected words",
        rects: [{ page: 1, x: 0.1, y: 0.1, width: 0.2, height: 0.05 }],
      });
    });

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
