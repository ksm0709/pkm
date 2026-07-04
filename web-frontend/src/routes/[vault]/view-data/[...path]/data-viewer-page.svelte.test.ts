// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { apiClient } from "$lib/api/client.js";
import { renderPdfIntoContainer } from "$lib/data-viewer/pdf-renderer";
import Page from "./+page.svelte";

const mockPage = vi.hoisted(() => {
  let value = { params: { vault: "taeho", path: "reports/deep.md" } };
  const subscribers = new Set<(next: typeof value) => void>();
  return {
    set(next: typeof value) {
      value = next;
      for (const subscriber of subscribers) subscriber(value);
    },
    subscribe(run: (next: typeof value) => void) {
      subscribers.add(run);
      run(value);
      return () => subscribers.delete(run);
    },
  };
});

vi.mock("$app/stores", () => ({ page: mockPage }));

vi.mock("$lib/api/client.js", () => ({
  apiClient: vi.fn(),
}));

vi.mock("$lib/data-viewer/pdf-renderer", () => ({
  renderPdfIntoContainer: vi.fn().mockResolvedValue(() => undefined),
}));

describe("data viewer page", () => {
  function readPageSource() {
    return readFileSync(
      "src/routes/[vault]/view-data/[...path]/+page.svelte",
      "utf-8",
    );
  }

  function styleRule(source: string, selectorPattern: RegExp) {
    const match = selectorPattern.exec(source);
    expect(match?.groups?.body).toBeDefined();
    return match?.groups?.body ?? "";
  }

  afterEach(() => {
    vi.mocked(apiClient).mockReset();
    vi.mocked(renderPdfIntoContainer).mockClear();
    mockPage.set({ params: { vault: "taeho", path: "reports/deep.md" } });
    document.body.innerHTML = "";
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

  it("renders markdown and PDF previews as full-bleed content surfaces", () => {
    const source = readPageSource();
    const contentOnlyRule = styleRule(
      source,
      /\.data-viewer\.content-only\s*\{(?<body>[^}]+)\}/m,
    );
    const previewRule = styleRule(source, /\.preview\s*\{(?<body>[^}]+)\}/m);
    const noticeRule = styleRule(source, /\.notice\s*\{(?<body>[^}]+)\}/m);

    expect(source).not.toContain("max-width: 1100px");
    expect(contentOnlyRule).toContain("height: 100%");
    expect(contentOnlyRule).toContain("min-height: 0");
    expect(contentOnlyRule).toContain("padding: 0");
    expect(previewRule).toContain("width: 100%");
    expect(previewRule).toContain("box-sizing: border-box");
    expect(previewRule).toContain("max-width: none");
    expect(previewRule).toContain("overflow-x: auto");
    expect(previewRule).not.toContain("border-radius");
    expect(previewRule).not.toContain("border: 1px");
    expect(previewRule).not.toContain("background: var(--surface");
    expect(noticeRule).toContain("border-radius: 12px");
  });

  it("fetches and renders markdown data files without the internal file header", async () => {
    vi.mocked(apiClient).mockResolvedValue(
      new Response("# Deep Report\n\n본문", { status: 200 }),
    );
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(Page, { target });

    await waitFor(() => {
      expect(target.querySelector(".markdown-preview h1")?.textContent).toBe(
        "Deep Report",
      );
    });

    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/taeho/data/reports/deep.md",
      expect.objectContaining({ method: "GET" }),
    );
    expect(target.querySelector(".viewer-header")).toBeNull();
    expect(
      target.querySelector<HTMLAnchorElement>('a[data-testid="raw-download"]'),
    ).toBeNull();

    unmount(component);
  });

  it("renders PDF data files through the authenticated PDF viewer", async () => {
    const bytes = new Uint8Array([37, 80, 68, 70]).buffer;
    mockPage.set({ params: { vault: "taeho", path: "reports/report.pdf" } });
    vi.mocked(apiClient).mockImplementation(async (url) => {
      if (String(url).includes("/data-annotations/")) {
        return new Response(
          JSON.stringify({
            version: 1,
            source_path: "reports/report.pdf",
            annotations: [],
          }),
          { status: 200 },
        );
      }
      return new Response(bytes.slice(0), { status: 200 });
    });
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(Page, { target });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
    });

    expect(target.querySelector('[data-testid="pdf-preview"]')).not.toBeNull();
    expect(target.querySelector(".viewer-header")).toBeNull();
    expect(target.querySelector(".markdown-preview")).toBeNull();
    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/taeho/data/reports/report.pdf",
      expect.objectContaining({ method: "GET" }),
    );

    unmount(component);
  });

  it("reloads the PDF viewer when navigating from one PDF data file to another", async () => {
    const bytes = new Uint8Array([37, 80, 68, 70]).buffer;
    mockPage.set({ params: { vault: "taeho", path: "reports/first.pdf" } });
    vi.mocked(apiClient).mockImplementation(async (url) => {
      if (String(url).includes("/data-annotations/")) {
        return new Response(
          JSON.stringify({ version: 1, source_path: "", annotations: [] }),
          { status: 200 },
        );
      }
      return new Response(bytes.slice(0), { status: 200 });
    });
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(Page, { target });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
    });

    mockPage.set({ params: { vault: "taeho", path: "reports/second.pdf" } });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(2);
    });
    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/taeho/data/reports/second.pdf",
      expect.objectContaining({ method: "GET" }),
    );
    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/taeho/data-annotations/reports/second.pdf",
      expect.objectContaining({ method: "GET" }),
    );

    unmount(component);
  });

  it("reloads the PDF viewer when navigating across vaults with the same PDF path", async () => {
    const bytes = new Uint8Array([37, 80, 68, 70]).buffer;
    mockPage.set({ params: { vault: "alpha", path: "reports/shared.pdf" } });
    vi.mocked(apiClient).mockImplementation(async (url) => {
      if (String(url).includes("/data-annotations/")) {
        return new Response(
          JSON.stringify({
            version: 1,
            source_path: "reports/shared.pdf",
            annotations: [],
          }),
          { status: 200 },
        );
      }
      return new Response(bytes.slice(0), { status: 200 });
    });
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(Page, { target });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(1);
    });

    mockPage.set({ params: { vault: "beta", path: "reports/shared.pdf" } });

    await waitFor(() => {
      expect(renderPdfIntoContainer).toHaveBeenCalledTimes(2);
    });
    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/beta/data/reports/shared.pdf",
      expect.objectContaining({ method: "GET" }),
    );
    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/beta/data-annotations/reports/shared.pdf",
      expect.objectContaining({ method: "GET" }),
    );

    unmount(component);
  });
});
