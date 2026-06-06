// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { apiClient } from "$lib/api/client.js";
import Page from "./+page.svelte";

vi.mock("$app/stores", async () => {
  const { readable } = await import("svelte/store");
  return {
    page: readable({ params: { vault: "taeho", path: "reports/deep.md" } }),
  };
});

vi.mock("$lib/api/client.js", () => ({
  apiClient: vi.fn(),
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

  it("keeps data previews full-width instead of capped at a centered readable width", () => {
    const source = readPageSource();
    const headerRule = styleRule(
      source,
      /\.viewer-header\s*\{(?<body>[^}]+)\}/m,
    );
    const previewRule = styleRule(
      source,
      /\.notice,\s*\.preview\s*\{(?<body>[^}]+)\}/m,
    );

    expect(source).not.toContain("max-width: 1100px");
    expect(headerRule).toContain("width: 100%");
    expect(headerRule).toContain("box-sizing: border-box");
    expect(headerRule).toContain("max-width: none");
    expect(previewRule).toContain("width: 100%");
    expect(previewRule).toContain("box-sizing: border-box");
    expect(previewRule).toContain("max-width: none");
    expect(previewRule).toContain("overflow-x: auto");
  });

  it("fetches and renders markdown data files with a raw download link", async () => {
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
    expect(
      target.querySelector<HTMLAnchorElement>('a[data-testid="raw-download"]')?.href,
    ).toContain("/api/v1/vault/taeho/data/reports/deep.md");

    unmount(component);
  });
});
