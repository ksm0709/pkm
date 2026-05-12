// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { goto } from "$app/navigation";
import { apiClient, apiGet } from "$lib/api/client.js";
import CmdK from "./CmdK.svelte";

vi.mock("$app/navigation", () => ({ goto: vi.fn() }));
vi.mock("$lib/api/client.js", () => ({ apiClient: vi.fn(), apiGet: vi.fn() }));

describe("CmdK", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(apiGet).mockImplementation(async (path: string) => {
      if (path === "/api/v1/vaults") return ["main", { name: "archive" }];
      if (path.includes("/search?q=pkm")) {
        return {
          results: [
            {
              note_id: "pkm-plan",
              title: "PKM Plan",
              snippet: "coverage plan",
            },
          ],
          query: "pkm",
          count: 1,
        };
      }
      if (path.includes("/tags/search?pattern=idea")) {
        return {
          pattern: "idea",
          mode: "glob",
          results: [
            {
              note_id: "idea-note",
              title: "Idea Note",
              tags: ["idea", "pkm"],
              path: "notes/idea-note.md",
            },
          ],
          count: 1,
        };
      }
      return [];
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.mocked(apiClient).mockReset();
    vi.mocked(goto).mockReset();
    vi.mocked(apiGet).mockReset();
    document.body.innerHTML = "";
  });

  function render(openToken = 1) {
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(CmdK, {
      target,
      props: {
        vaultName: "main",
        openToken,
      },
    });
    return { target, component };
  }

  async function flush() {
    await Promise.resolve();
    await Promise.resolve();
    await tick();
  }

  it("opens from its token, renders command rows, and navigates selected static commands", async () => {
    const { target, component } = render();
    await tick();
    await vi.runOnlyPendingTimersAsync();
    await tick();

    expect(
      target.querySelector('[role="dialog"]')?.getAttribute("aria-label"),
    ).toBe("Command palette");
    const labels = [...target.querySelectorAll(".row-label")].map(
      (node) => node.textContent,
    );
    expect(labels).toContain("Open notes");
    expect(labels).toContain("Switch vault…");

    const openNotes = [
      ...target.querySelectorAll<HTMLElement>(".cmdk-row"),
    ].find((row) => row.textContent?.includes("Open notes"));
    openNotes?.click();
    await tick();

    expect(goto).toHaveBeenCalledWith("/main");
    expect(target.querySelector('[role="dialog"]')).toBeNull();

    unmount(component);
  });

  it("debounces note search and opens the selected note result", async () => {
    const { target, component } = render();
    await tick();
    await vi.runOnlyPendingTimersAsync();
    await tick();

    const input = target.querySelector<HTMLInputElement>(".cmdk-input");
    input!.value = "pkm";
    input!.dispatchEvent(new Event("input", { bubbles: true }));
    await tick();
    await vi.advanceTimersByTimeAsync(120);
    await tick();

    expect(apiGet).toHaveBeenCalledWith("/api/v1/vault/main/search?q=pkm");
    expect(
      target.querySelector('.cmdk-row[data-note-id="pkm-plan"]')?.textContent,
    ).toContain("PKM Plan");

    window.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Enter",
        bubbles: true,
        cancelable: true,
      }),
    );
    await tick();

    expect(goto).toHaveBeenCalledWith("/main/notes/pkm-plan");
    expect(target.querySelector('[role="dialog"]')).toBeNull();

    unmount(component);
  });

  it("falls back to the note list when backend search is unavailable", async () => {
    vi.mocked(apiGet).mockImplementation(async (path: string) => {
      if (path === "/api/v1/vaults") return ["main"];
      if (path.includes("/search?q=research")) {
        throw new Error("GET search -> 404");
      }
      if (path === "/api/v1/vault/main/notes") {
        return [
          {
            note_id: "fallback-research-note",
            title: "Fallback Research Note",
            path: "notes/fallback-research-note.md",
            description: "Searchable note from fallback.",
            tags: ["research"],
          },
          {
            note_id: "unrelated",
            title: "Unrelated",
            path: "notes/unrelated.md",
            description: "Different note.",
            tags: [],
          },
        ];
      }
      return [];
    });
    const { target, component } = render();
    await tick();
    await vi.runOnlyPendingTimersAsync();
    await tick();

    const input = target.querySelector<HTMLInputElement>(".cmdk-input");
    input!.value = "research";
    input!.dispatchEvent(new Event("input", { bubbles: true }));
    await tick();
    await vi.advanceTimersByTimeAsync(120);
    await flush();

    expect(apiGet).toHaveBeenCalledWith("/api/v1/vault/main/search?q=research");
    expect(apiGet).toHaveBeenCalledWith("/api/v1/vault/main/notes");
    expect(
      target.querySelector(".cmdk-row[data-note-id='fallback-research-note']")
        ?.textContent,
    ).toContain("Fallback Research Note");
    expect(
      target.querySelector(".cmdk-row[data-note-id='unrelated']"),
    ).toBeNull();

    unmount(component);
  });

  it("searches tag rows and routes their note result", async () => {
    const { target, component } = render();
    await tick();
    await vi.runOnlyPendingTimersAsync();
    await tick();

    const input = target.querySelector<HTMLInputElement>(".cmdk-input");
    input!.value = "#idea";
    input!.dispatchEvent(new Event("input", { bubbles: true }));
    await tick();
    await vi.advanceTimersByTimeAsync(120);
    await tick();

    expect(apiGet).toHaveBeenCalledWith(
      "/api/v1/vault/main/tags/search?pattern=idea",
    );
    const row = target.querySelector<HTMLElement>(
      '.cmdk-row[data-note-id="idea-note"]',
    );
    expect(row?.textContent).toContain("#idea #pkm");

    row?.click();
    await tick();
    expect(goto).toHaveBeenCalledWith("/main/notes/idea-note");

    unmount(component);
  });

  it("dispatches theme changes through the shared theme event", async () => {
    const { target, component } = render();
    const listener = vi.fn();
    vi.stubGlobal("localStorage", {
      getItem: vi.fn(() => "auto"),
    });
    window.addEventListener("pkm:theme-change", listener);
    await tick();
    await vi.runOnlyPendingTimersAsync();
    await tick();

    const themeRow = [
      ...target.querySelectorAll<HTMLElement>(".cmdk-row"),
    ].find((row) => row.textContent?.includes("Toggle theme"));
    themeRow?.click();

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail).toEqual({ theme: "light" });

    window.removeEventListener("pkm:theme-change", listener);
    unmount(component);
  });

  it("lists Add daily sub-note as a command and opens the created note", async () => {
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "meeting notes"),
    );
    vi.mocked(apiClient).mockResolvedValue(
      new Response(JSON.stringify({ note_id: "2026-05-12-meeting-notes" }), {
        status: 201,
      }),
    );
    const { target, component } = render();
    await tick();
    await vi.runOnlyPendingTimersAsync();
    await tick();

    const labels = [...target.querySelectorAll(".row-label")].map(
      (node) => node.textContent,
    );
    expect(labels).toContain("Add daily sub-note");

    const subnoteCommand = [
      ...target.querySelectorAll<HTMLElement>(".cmdk-row"),
    ].find((row) => row.textContent?.includes("Add daily sub-note"));
    subnoteCommand?.click();
    await flush();

    expect(prompt).toHaveBeenCalledWith("Subnote title");
    expect(apiClient).toHaveBeenCalledWith("/api/v1/vault/main/daily/today", {
      method: "POST",
      body: JSON.stringify({
        type: "subnote",
        title: "meeting notes",
        content: "",
      }),
    });
    expect(goto).toHaveBeenCalledWith("/main/notes/2026-05-12-meeting-notes");
    await flush();
    expect(target.querySelector('[role="dialog"]')).toBeNull();

    unmount(component);
  });

  it("lists Index vault as a command and rebuilds the vault index", async () => {
    vi.mocked(apiClient).mockResolvedValue(
      new Response(JSON.stringify({ status: "ok", count: 3 }), {
        status: 200,
      }),
    );
    const { target, component } = render();
    await tick();
    await vi.runOnlyPendingTimersAsync();
    await tick();

    const labels = [...target.querySelectorAll(".row-label")].map(
      (node) => node.textContent,
    );
    expect(labels).toContain("Index vault");

    const indexCommand = [
      ...target.querySelectorAll<HTMLElement>(".cmdk-row"),
    ].find((row) => row.textContent?.includes("Index vault"));
    indexCommand?.click();
    await flush();

    expect(apiClient).toHaveBeenCalledWith("/api/v1/vault/main/index", {
      method: "POST",
    });
    expect(goto).toHaveBeenCalledWith("/main/graph");
    expect(target.querySelector('[role="dialog"]')).toBeNull();

    unmount(component);
  });
});
