// @vitest-environment jsdom
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
