// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createRawSnippet, mount, tick, unmount } from "svelte";
import { graphKeyNav } from "$lib/navigation/graph-keynav.svelte";
import Layout from "./+layout.svelte";

const mocks = vi.hoisted(() => ({
  apiClient: vi.fn(),
  apiGet: vi.fn(),
  goto: vi.fn(),
  loadConfigs: vi.fn(),
  pageStore: undefined as
    | undefined
    | {
        set: (value: { params: { vault: string }; url: URL }) => void;
        subscribe: (run: (value: unknown) => void) => () => void;
      },
}));

vi.mock("$app/navigation", () => ({ goto: mocks.goto }));
vi.mock("$lib/api/client.js", () => ({
  apiClient: mocks.apiClient,
  apiGet: mocks.apiGet,
}));
vi.mock("$lib/configs/client", () => ({
  loadConfigs: mocks.loadConfigs,
}));
vi.mock("$app/stores", async () => {
  const { writable } = await import("svelte/store");
  mocks.pageStore = writable({
    params: { vault: "main" },
    url: new URL("http://localhost/main"),
  });
  return {
    page: { subscribe: mocks.pageStore.subscribe },
  };
});

describe("vault layout goto key hints", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-05-12T09:00:00.000Z"));
    mocks.loadConfigs.mockResolvedValue({ settings: [] });
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe = vi.fn();
        disconnect = vi.fn();
      },
    );
    graphKeyNav.resetForTests();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    graphKeyNav.resetForTests();
    document.documentElement.removeAttribute("style");
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
    const children = createRawSnippet(() => ({
      render: () => '<main data-testid="child">Child</main>',
    }));
    const component = mount(Layout, { target, props: { children } });
    return { component, target };
  }

  async function press(
    key: string,
    target: EventTarget = window,
    init: KeyboardEventInit = {},
  ) {
    const event = new KeyboardEvent("keydown", {
      key,
      bubbles: true,
      cancelable: true,
      ...init,
    });
    target.dispatchEvent(event);
    await tick();
    return event;
  }

  function hint() {
    return document.querySelector('[aria-label="Key sequence hints"]');
  }

  it("shows goto hints after pressing g", async () => {
    const { component } = render();
    await flush();

    await press("g");

    expect(hint()?.textContent).toContain("g");
    expect(hint()?.textContent).toContain("d");
    expect(hint()?.textContent).toContain("Open daily note");
    expect(hint()?.textContent).not.toContain("Follow link at cursor");
    expect(hint()?.textContent).not.toContain("Open external link");

    unmount(component);
  });

  it("shows ranked semantic note hints and follows g-number", async () => {
    graphKeyNav.setCurrentNoteNavigationContext("main", "source-note", [
      { note_id: "third", title: "Third", confidence: 0.7 },
      { note_id: "beta", title: "Beta", confidence: 0.9 },
      { note_id: "alpha", title: "Alpha", confidence: 0.9 },
    ]);
    const { component } = render();
    await flush();

    await press("g");

    expect(hint()?.textContent).toContain("n");
    expect(hint()?.textContent).toContain("Next semantic neighbor");
    expect(hint()?.textContent).toContain("p");
    expect(hint()?.textContent).toContain("Previous semantic neighbor");
    expect(hint()?.textContent).toContain("1");
    expect(hint()?.textContent).toContain("Alpha");
    expect(hint()?.textContent).toContain("0.90");
    expect(hint()?.textContent).toContain("2");
    expect(hint()?.textContent).toContain("Beta");

    const event = await press("1");

    expect(event.defaultPrevented).toBe(true);
    expect(mocks.goto).toHaveBeenCalledWith("/main/notes/alpha");
    expect(hint()).toBeNull();

    unmount(component);
  });

  it("ignores unavailable semantic ranks without preventing defaults", async () => {
    graphKeyNav.setCurrentNoteNavigationContext("main", "source-note", [
      { note_id: "alpha", title: "Alpha", confidence: 0.9 },
    ]);
    const { component } = render();
    await flush();

    await press("g");
    const event = await press("9");

    expect(event.defaultPrevented).toBe(false);
    expect(mocks.goto).not.toHaveBeenCalled();
    expect(hint()).toBeNull();

    unmount(component);
  });

  it("runs gn, gp, gb, and Ctrl+O through the navigation stack", async () => {
    graphKeyNav.setCurrentNoteNavigationContext("main", "source-note", [
      { note_id: "alpha", title: "Alpha", confidence: 0.9 },
      { note_id: "beta", title: "Beta", confidence: 0.8 },
    ]);
    const { component } = render();
    await flush();

    await press("g");
    await press("n");
    expect(mocks.goto).toHaveBeenLastCalledWith("/main/notes/alpha");

    mocks.goto.mockClear();
    await press("g");
    await press("p");
    expect(mocks.goto).toHaveBeenLastCalledWith("/main/notes/beta");

    mocks.goto.mockClear();
    await press("g");
    await press("b");
    expect(mocks.goto).toHaveBeenLastCalledWith("/main/notes/source-note");

    graphKeyNav.setCurrentNoteNavigationContext("main", "source-note", [
      { note_id: "alpha", title: "Alpha", confidence: 0.9 },
    ]);
    await press("g");
    await press("1");
    mocks.goto.mockClear();

    const ctrlO = await press("o", window, { ctrlKey: true, code: "KeyO" });
    expect(ctrlO.defaultPrevented).toBe(true);
    expect(mocks.goto).toHaveBeenLastCalledWith("/main/notes/source-note");

    mocks.goto.mockClear();
    const emptyCtrlO = await press("o", window, {
      ctrlKey: true,
      code: "KeyO",
    });
    expect(emptyCtrlO.defaultPrevented).toBe(false);
    expect(mocks.goto).not.toHaveBeenCalled();

    unmount(component);
  });

  it("shows leader hints after pressing Space", async () => {
    const { component } = render();
    await flush();

    await press(" ");

    expect(hint()?.textContent).toContain("Space");
    expect(hint()?.textContent).toContain("k");
    expect(hint()?.textContent).toContain("Open command palette");
    expect(hint()?.textContent).toContain("/");
    expect(hint()?.textContent).toContain("Jump to note");
    expect(hint()?.textContent).toContain("g");
    expect(hint()?.textContent).toContain("Open graph");
    expect(hint()?.textContent).toContain("v");
    expect(hint()?.textContent).toContain("Switch vault");

    unmount(component);
  });

  it("runs gd and clears the popup", async () => {
    const { component } = render();
    await flush();

    await press("g");
    const event = await press("d");

    expect(event.defaultPrevented).toBe(true);
    expect(mocks.goto).toHaveBeenCalledWith("/main/notes/2026-05-12");
    expect(hint()).toBeNull();

    unmount(component);
  });

  it("runs Space command shortcuts through CmdK command routing", async () => {
    const { component } = render();
    await flush();

    await press(" ");
    const event = await press("g");

    expect(event.defaultPrevented).toBe(true);
    expect(hint()).toBeNull();
    expect(mocks.goto).toHaveBeenCalledWith("/main/graph");

    unmount(component);
  });

  it("runs Space slash and opens note search", async () => {
    const { component, target } = render();
    await flush();

    await press(" ");
    const event = await press("/");

    expect(event.defaultPrevented).toBe(true);
    expect(hint()).toBeNull();
    expect(target.querySelector('[role="dialog"]')).not.toBeNull();
    expect(target.querySelector(".console-label")?.textContent).toContain(
      "NOTE SEARCH",
    );

    unmount(component);
  });

  it("runs Space k and clears the popup", async () => {
    const { component, target } = render();
    await flush();

    await press(" ");
    const event = await press("k");

    expect(event.defaultPrevented).toBe(true);
    expect(hint()).toBeNull();
    expect(target.querySelector('[role="dialog"]')).not.toBeNull();

    unmount(component);
  });

  it("dismisses the hint on Escape, unsupported keys, and timeout", async () => {
    const { component } = render();
    await flush();

    await press("g");
    await press("Escape");
    expect(hint()).toBeNull();
    expect(mocks.goto).not.toHaveBeenCalled();

    await press("g");
    await press("z");
    expect(hint()).toBeNull();
    expect(mocks.goto).not.toHaveBeenCalled();

    await press("g");
    vi.advanceTimersByTime(1199);
    await tick();
    expect(hint()).not.toBeNull();

    vi.advanceTimersByTime(1);
    await tick();
    expect(hint()).toBeNull();

    unmount(component);
  });

  it("does not show hints while typing or while a dialog is open", async () => {
    const { component } = render();
    await flush();

    const input = document.createElement("input");
    document.body.appendChild(input);
    await press("g", input);
    expect(hint()).toBeNull();

    const editor = document.createElement("div");
    editor.className = "cm-editor";
    const editorChild = document.createElement("span");
    editor.appendChild(editorChild);
    document.body.appendChild(editor);
    await press("g", editorChild);
    expect(hint()).toBeNull();

    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-label", "Command palette");
    document.body.appendChild(dialog);
    await press("g");
    expect(hint()).toBeNull();

    unmount(component);
  });

  it("does not advertise retired Ask or Workflow leader shortcuts", async () => {
    const { component } = render();
    await flush();

    await press(" ");
    const text = hint()?.textContent ?? "";

    unmount(component);

    expect(text).not.toMatch(/Ask…|Open ask|Open workflows/);
  });
});
