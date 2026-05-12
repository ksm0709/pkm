// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { goto } from "$app/navigation";
import { mount, tick, unmount } from "svelte";
import { apiClient, apiGet } from "$lib/api/client.js";
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
  apiGet: vi.fn(),
}));

describe("logger page", () => {
  beforeEach(() => {
    vi.mocked(apiGet).mockResolvedValue({
      note_id: "2026-05-12",
      title: "2026-05-12",
      body: "## Logs\n- [09:00:00] Started logging",
    });
  });

  afterEach(() => {
    vi.mocked(apiClient).mockReset();
    vi.mocked(apiGet).mockReset();
    vi.mocked(goto).mockReset();
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  async function flush() {
    await Promise.resolve();
    await Promise.resolve();
    await tick();
  }

  function render() {
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(Page, { target });
    return { target, component };
  }

  it("opens logger actions from the plus button and creates a daily sub-note", async () => {
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "research notes"),
    );
    vi.mocked(apiClient).mockResolvedValue(
      new Response(JSON.stringify({ note_id: "2026-05-12-research-notes" }), {
        status: 201,
      }),
    );
    const { target, component } = render();
    await flush();

    const actionsButton = target.querySelector<HTMLButtonElement>(
      'button[aria-label="Open logger actions"]',
    );
    expect(actionsButton).not.toBeNull();
    actionsButton?.click();
    await tick();

    const subnoteAction = target.querySelector<HTMLButtonElement>(
      'button[aria-label="Add sub-note"]',
    );
    expect(subnoteAction?.textContent).toContain("Add sub-note");
    subnoteAction?.click();
    await flush();

    expect(prompt).toHaveBeenCalledWith("Subnote title");
    expect(apiClient).toHaveBeenCalledWith("/api/v1/vault/main/daily/today", {
      method: "POST",
      body: JSON.stringify({
        type: "subnote",
        title: "research notes",
        content: "",
      }),
    });
    expect(goto).toHaveBeenCalledWith("/main/notes/2026-05-12-research-notes");
    expect(target.querySelector('[role="menu"]')).toBeNull();

    unmount(component);
  });
});
