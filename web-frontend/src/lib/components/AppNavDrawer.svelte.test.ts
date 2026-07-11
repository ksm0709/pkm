// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { goto } from "$app/navigation";
import AppNavDrawer from "./AppNavDrawer.svelte";

vi.mock("$app/navigation", () => ({ goto: vi.fn() }));
vi.mock("$app/stores", () => ({
  page: {
    subscribe(run: (value: { url: URL }) => void) {
      run({ url: new URL("http://localhost/main/tags") });
      return () => {};
    },
  },
}));

describe("AppNavDrawer", () => {
  afterEach(() => {
    vi.mocked(goto).mockReset();
    document.body.innerHTML = "";
  });

  it("renders vault navigation with the active route and closed-drawer tab stops", async () => {
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(AppNavDrawer, {
      target,
      props: {
        vaultName: "main",
        open: false,
      },
    });
    await tick();

    const drawer = target.querySelector("aside");
    expect(drawer?.getAttribute("aria-hidden")).toBe("true");
    expect(target.querySelector(".drawer-count")?.textContent).toBe(
      "7 channels",
    );

    const buttons = [
      ...target.querySelectorAll<HTMLButtonElement>(".nav-item"),
    ];
    expect(buttons.map((button) => button.getAttribute("aria-label"))).toEqual([
      "Notes",
      "Search",
      "Tags",
      "Graph",
      "Logger",
      "Daily",
      "Configs",
    ]);
    expect(buttons.every((button) => button.tabIndex === -1)).toBe(true);

    const tagsButton = buttons.find(
      (button) => button.getAttribute("aria-label") === "Tags",
    );
    expect(tagsButton?.getAttribute("aria-current")).toBe("page");

    unmount(component);
  });

  it("opens note search from the Search navigation item without routing", async () => {
    const target = document.createElement("div");
    const openCommandPalette = vi.fn();
    const openNoteSearch = vi.fn();
    const closeDrawer = vi.fn();
    document.body.appendChild(target);

    const component = mount(AppNavDrawer, {
      target,
      props: {
        vaultName: "main",
        open: true,
        openCommandPalette,
        openNoteSearch,
        closeDrawer,
      },
    });
    await tick();

    const searchButton = [
      ...target.querySelectorAll<HTMLButtonElement>(".nav-item"),
    ].find((button) => button.getAttribute("aria-label") === "Search");
    expect(searchButton?.tabIndex).toBe(0);

    searchButton?.click();

    expect(closeDrawer).toHaveBeenCalledTimes(1);
    expect(openNoteSearch).toHaveBeenCalledTimes(1);
    expect(openCommandPalette).not.toHaveBeenCalled();
    expect(goto).not.toHaveBeenCalled();

    unmount(component);
  });

  it("closes the drawer and routes when users choose a destination", async () => {
    const target = document.createElement("div");
    const closeDrawer = vi.fn();
    document.body.appendChild(target);

    const component = mount(AppNavDrawer, {
      target,
      props: {
        vaultName: "main",
        open: true,
        closeDrawer,
      },
    });
    await tick();

    const graphButton = [
      ...target.querySelectorAll<HTMLButtonElement>(".nav-item"),
    ].find((button) => button.getAttribute("aria-label") === "Graph");
    graphButton?.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Enter",
        bubbles: true,
        cancelable: true,
      }),
    );

    expect(closeDrawer).toHaveBeenCalledTimes(1);
    expect(goto).toHaveBeenCalledWith("/main/graph");

    unmount(component);
  });
});
