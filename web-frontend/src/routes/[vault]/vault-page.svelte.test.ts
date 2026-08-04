// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { goto } from "$app/navigation";
import { mount, tick, unmount } from "svelte";
import { apiClient, apiGet } from "$lib/api/client.js";
import Page from "./+page.svelte";

vi.mock("$app/navigation", () => ({ goto: vi.fn() }));
vi.mock("$app/stores", async () => {
  const { readable } = await import("svelte/store");
  return { page: readable({ params: { vault: "main" } }) };
});
vi.mock("$lib/api/client.js", () => ({
  apiClient: vi.fn(),
  apiGet: vi.fn(),
}));

describe("vault notes page", () => {
  beforeEach(() => {
    vi.mocked(apiGet).mockResolvedValue([]);
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

  it("creates a general note from the visible Add note button and opens it", async () => {
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "Research plan"),
    );
    vi.mocked(apiClient).mockResolvedValue(
      new Response(JSON.stringify({ note_id: "research-plan" }), {
        status: 201,
      }),
    );
    const { target, component } = render();
    await flush();

    const addNote = target.querySelector<HTMLButtonElement>(
      'button[aria-label="Add note"]',
    );
    expect(addNote).not.toBeNull();
    expect(addNote?.textContent).toContain("Add note");
    addNote?.click();

    await waitFor(() => {
      expect(apiClient).toHaveBeenCalledWith("/api/v1/vault/main/notes", {
        method: "POST",
        body: JSON.stringify({ title: "Research plan", body: "", tags: [] }),
      });
    });
    await waitFor(() => {
      expect(goto).toHaveBeenCalledWith("/main/notes/research-plan");
    });

    unmount(component);
  });

  it("does not create a note when the prompted title is cancelled, empty, or whitespace", async () => {
    vi.stubGlobal(
      "prompt",
      vi
        .fn()
        .mockReturnValueOnce(null)
        .mockReturnValueOnce("")
        .mockReturnValueOnce("   "),
    );
    const { target, component } = render();
    await flush();

    const addNote = target.querySelector<HTMLButtonElement>(
      'button[aria-label="Add note"]',
    );
    addNote?.click();
    addNote?.click();
    addNote?.click();
    await flush();

    expect(apiClient).not.toHaveBeenCalled();

    unmount(component);
  });

  it("does not prompt or post again while a note creation request is pending", async () => {
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "Research plan"),
    );
    vi.mocked(apiClient).mockReturnValueOnce(new Promise(() => {}));
    const { target, component } = render();
    await flush();

    const addNote = target.querySelector<HTMLButtonElement>(
      'button[aria-label="Add note"]',
    );
    addNote?.click();
    await waitFor(() => {
      expect(apiClient).toHaveBeenCalledTimes(1);
    });

    addNote?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flush();

    expect(prompt).toHaveBeenCalledTimes(1);
    expect(apiClient).toHaveBeenCalledTimes(1);

    unmount(component);
  });

  it("shows a rejected create request error and clears the creation state", async () => {
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "Research plan"),
    );
    vi.mocked(apiClient).mockRejectedValue(new Error("network unavailable"));
    const { target, component } = render();
    await flush();

    const addNote = target.querySelector<HTMLButtonElement>(
      'button[aria-label="Add note"]',
    );
    addNote?.click();

    await waitFor(() => {
      expect(target.querySelector(".status-msg.error")?.textContent).toContain(
        "network unavailable",
      );
    });
    expect(addNote?.disabled).toBe(false);

    unmount(component);
  });

  it("shows a visible error when creating a note returns a bad HTTP response", async () => {
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "Research plan"),
    );
    vi.mocked(apiClient).mockResolvedValue(
      new Response("failure", { status: 500 }),
    );
    const { target, component } = render();
    await flush();

    target
      .querySelector<HTMLButtonElement>('button[aria-label="Add note"]')
      ?.click();

    await waitFor(() => {
      const status = target.querySelector(".status-msg.error");
      expect(status).not.toBeNull();
      expect(status?.textContent).toContain("POST note -> 500");
    });

    unmount(component);
  });

  it("shows a creation failure instead of Loading while the initial notes request is pending", async () => {
    vi.mocked(apiGet).mockReturnValueOnce(new Promise(() => {}));
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "Research plan"),
    );
    vi.mocked(apiClient).mockRejectedValue(new Error("network unavailable"));
    const { target, component } = render();

    await waitFor(() => {
      expect(target.textContent).toContain("Loading…");
    });
    target
      .querySelector<HTMLButtonElement>('button[aria-label="Add note"]')
      ?.click();

    await waitFor(() => {
      expect(target.querySelector(".status-msg.error")?.textContent).toContain(
        "network unavailable",
      );
    });
    expect(target.textContent).not.toContain("Loading…");

    unmount(component);
  });

  it("shows a visible error when a new note response omits note_id", async () => {
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "Research plan"),
    );
    vi.mocked(apiClient).mockResolvedValue(
      new Response(JSON.stringify({}), { status: 201 }),
    );
    const { target, component } = render();
    await flush();

    target
      .querySelector<HTMLButtonElement>('button[aria-label="Add note"]')
      ?.click();

    await waitFor(() => {
      const status = target.querySelector(".status-msg.error");
      expect(status?.textContent).toContain("POST note -> missing note_id");
    });
    expect(goto).not.toHaveBeenCalled();

    unmount(component);
  });
});
