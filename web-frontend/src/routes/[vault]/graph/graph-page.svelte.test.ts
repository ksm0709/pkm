// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { apiClient } from "$lib/api/client.js";
import Page from "./+page.svelte";

vi.mock("$app/navigation", () => ({ goto: vi.fn() }));
vi.mock("$app/stores", async () => {
  const { readable } = await import("svelte/store");
  return {
    page: readable({ params: { vault: "main" } }),
  };
});
vi.mock("$lib/api/client.js", () => ({
  apiClient: vi.fn(),
}));

describe("graph page", () => {
  beforeEach(() => {
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      return window.setTimeout(() => callback(0), 0);
    });
    vi.stubGlobal("cancelAnimationFrame", (id: number) => {
      window.clearTimeout(id);
    });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      setTransform: vi.fn(),
      clearRect: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
      arc: vi.fn(),
      fill: vi.fn(),
      fillText: vi.fn(),
    } as unknown as CanvasRenderingContext2D);
  });

  afterEach(() => {
    vi.mocked(apiClient).mockReset();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  async function flush() {
    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    await tick();
  }

  async function waitFor(assertion: () => void | Promise<void>) {
    let lastError: unknown;
    for (let i = 0; i < 30; i += 1) {
      try {
        await assertion();
        return;
      } catch (error) {
        lastError = error;
        await flush();
      }
    }
    throw lastError;
  }

  function render() {
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(Page, { target });
    return { target, component };
  }

  it("renders graph note preview body as markdown", async () => {
    vi.mocked(apiClient).mockImplementation(async (url: string | URL) => {
      const path = String(url);
      if (path.endsWith("/graph")) {
        return new Response(
          JSON.stringify({
            nodes: [
              { id: "markdown-note", title: "Markdown Note", type: "note" },
            ],
            edges: [],
          }),
          { status: 200 },
        );
      }
      if (path.endsWith("/notes/markdown-note")) {
        return new Response(
          JSON.stringify({
            title: "Markdown Note",
            body: "## Preview\n\nRead **this** with [[Target]] and &depends_on [[Other]].",
          }),
          { status: 200 },
        );
      }
      return new Response("not found", { status: 404 });
    });

    const { target, component } = render();
    await waitFor(() => {
      expect(
        target.querySelector<HTMLInputElement>(
          'input[aria-label="Search graph nodes"]',
        ),
      ).not.toBeNull();
    });

    const search = target.querySelector<HTMLInputElement>(
      'input[aria-label="Search graph nodes"]',
    );
    search!.value = "markdown";
    search!.dispatchEvent(new Event("input", { bubbles: true }));
    await waitFor(() => {
      expect(
        [...target.querySelectorAll("button")].some((button) =>
          button.textContent?.includes("Focus Markdown Note"),
        ),
      ).toBe(true);
    });

    const focusButton = [...target.querySelectorAll("button")].find((button) =>
      button.textContent?.includes("Focus Markdown Note"),
    );
    focusButton?.click();
    await waitFor(() => {
      expect(
        [...target.querySelectorAll("button")].some((button) =>
          button.textContent?.includes("Preview focused note"),
        ),
      ).toBe(true);
    });

    const previewButton = [...target.querySelectorAll("button")].find(
      (button) => button.textContent?.includes("Preview focused note"),
    );
    previewButton?.click();
    await waitFor(() => {
      expect(
        target.querySelector(
          '[data-testid="graph-preview-sheet"] .preview-body h2',
        )?.textContent,
      ).toBe("Preview");
    });

    const sheet = target.querySelector('[data-testid="graph-preview-sheet"]');
    expect(sheet?.querySelector("pre.preview-body")).toBeNull();
    expect(sheet?.querySelector("strong")?.textContent).toBe("this");
    expect(
      sheet?.querySelector<HTMLAnchorElement>('a[href="/main/notes/Target"]')
        ?.textContent,
    ).toBe("Target");
    expect(sheet?.querySelector(".note-relation-chip")?.textContent).toBe(
      "&depends_on",
    );

    unmount(component);
  });
});
