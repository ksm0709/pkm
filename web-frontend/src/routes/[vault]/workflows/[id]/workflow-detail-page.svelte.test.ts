// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { apiGet } from "$lib/api/client.js";
import Page from "./+page.svelte";

vi.mock("$app/stores", async () => {
  const { readable } = await import("svelte/store");
  return {
    page: readable({
      params: { vault: "main", id: "zettelkasten_maintenance" },
    }),
  };
});

vi.mock("$lib/api/client.js", () => ({
  apiClient: vi.fn(),
  apiGet: vi.fn(),
}));

describe("workflow detail page", () => {
  afterEach(() => {
    vi.mocked(apiGet).mockReset();
    document.body.innerHTML = "";
  });

  async function waitFor(assertion: () => void | Promise<void>) {
    let lastError: unknown;
    for (let i = 0; i < 25; i += 1) {
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

  function render() {
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(Page, { target });
    return { target, component };
  }

  it("renders workflow body as markdown instead of raw preformatted text", async () => {
    vi.mocked(apiGet).mockImplementation(async (url: string) => {
      if (url.endsWith("/run-status")) {
        return { status: "idle", task_id: null };
      }
      return {
        id: "zettelkasten_maintenance",
        title: "Zettelkasten maintenance",
        trigger_time: "09:00",
        schedule_hour: 9,
        enabled: true,
        marker_file: ".pkm/workflow.marker",
        pre_hook: null,
        post_hook: null,
        snippet: "Maintain graph",
        body: "## Steps\n\n- Review **knowledge** linked to [[Hub Note]].\n- &supports [[Leaf Note]]",
        jitter_type: "daily",
      };
    });

    const { target, component } = render();
    await waitFor(() => {
      expect(target.querySelector(".workflow-body h2")?.textContent).toBe(
        "Steps",
      );
    });

    const body = target.querySelector(".workflow-body");
    expect(body?.querySelector("pre")).toBeNull();
    expect(body?.querySelector("strong")?.textContent).toBe("knowledge");
    expect(
      body?.querySelector<HTMLAnchorElement>('a[href="/main/notes/Hub%20Note"]')
        ?.textContent,
    ).toBe("Hub Note");
    expect(body?.querySelector(".note-relation-chip")?.textContent).toBe(
      "&supports",
    );

    unmount(component);
  });
});
