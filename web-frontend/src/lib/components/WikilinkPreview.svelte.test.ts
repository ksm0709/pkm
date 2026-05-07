// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { apiGet } from "$lib/api/client.js";
import WikilinkPreview from "./WikilinkPreview.svelte";

vi.mock("$lib/api/client.js", () => ({ apiGet: vi.fn() }));

describe("WikilinkPreview", () => {
  beforeEach(() => {
    vi.mocked(apiGet).mockResolvedValue({
      title: "Fetched Title",
      body: "A".repeat(700),
    });
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 400,
    });
    Object.defineProperty(window, "innerHeight", {
      configurable: true,
      value: 260,
    });
  });

  afterEach(() => {
    vi.mocked(apiGet).mockReset();
    document.body.innerHTML = "";
    delete (window as any).__pkmPreview;
  });

  function render() {
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(WikilinkPreview, {
      target,
      props: {
        vault: "main vault",
      },
    });
    return { target, component };
  }

  it("registers the preview bus, clamps placement, fetches body lazily, and hides on request", async () => {
    const { target, component } = render();
    await tick();

    expect((window as any).__pkmPreview.show).toEqual(expect.any(Function));
    (window as any).__pkmPreview.show({
      id: "note/id",
      title: "",
      x: 390,
      y: 250,
    });
    await Promise.resolve();
    await tick();

    expect(apiGet).toHaveBeenCalledWith(
      "/api/v1/vault/main%20vault/notes/note%2Fid",
    );
    const preview = target.querySelector<HTMLElement>(".wl-preview");
    expect(preview?.getAttribute("role")).toBe("tooltip");
    expect(preview?.style.left).toBe("32px");
    expect(preview?.style.top).toBe("18px");
    expect(target.querySelector(".wl-title")?.textContent).toBe("note/id");
    expect(target.querySelector(".wl-body")?.textContent).toHaveLength(600);

    (window as any).__pkmPreview.hide();
    await tick();
    expect(target.querySelector(".wl-preview")).toBeNull();

    unmount(component);
    expect((window as any).__pkmPreview).toBeUndefined();
  });

  it("uses cached body on repeated show and renders empty state after fetch failure", async () => {
    const { target, component } = render();
    await tick();

    (window as any).__pkmPreview.show({
      id: "cached",
      title: "Cached",
      x: 10,
      y: 10,
    });
    await Promise.resolve();
    await tick();
    (window as any).__pkmPreview.hide();
    await tick();
    (window as any).__pkmPreview.show({
      id: "cached",
      title: "Cached again",
      x: 10,
      y: 10,
    });
    await Promise.resolve();
    await tick();

    expect(apiGet).toHaveBeenCalledTimes(1);
    expect(target.querySelector(".wl-body")?.textContent).toHaveLength(600);

    vi.mocked(apiGet).mockRejectedValueOnce(new Error("offline"));
    (window as any).__pkmPreview.show({
      id: "missing",
      title: "Missing",
      x: 10,
      y: 10,
    });
    await Promise.resolve();
    await tick();

    expect(target.querySelector(".wl-empty")?.textContent).toBe("(empty)");

    unmount(component);
  });
});
