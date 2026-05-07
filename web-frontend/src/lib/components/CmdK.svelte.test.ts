// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { goto } from "$app/navigation";
import { apiGet } from "$lib/api/client.js";
import CmdK from "./CmdK.svelte";

vi.mock("$app/navigation", () => ({ goto: vi.fn() }));
vi.mock("$lib/api/client.js", () => ({ apiGet: vi.fn() }));

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
});
