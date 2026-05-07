// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import ThemeProvider from "./ThemeProvider.svelte";

describe("ThemeProvider", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.documentElement.removeAttribute("data-theme");
    document.body.innerHTML = "";
    localStorage.clear();
  });

  function render() {
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(ThemeProvider, { target });
    return { component };
  }

  it("applies a stored explicit theme on mount", async () => {
    localStorage.setItem("pkm.theme", "light");
    const { component } = render();
    await tick();

    expect(document.documentElement.getAttribute("data-theme")).toBe("light");

    unmount(component);
  });

  it("stores palette events and removes the attribute for auto theme", async () => {
    const { component } = render();
    await tick();

    window.dispatchEvent(
      new CustomEvent("pkm:theme-change", { detail: { theme: "dark" } }),
    );
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("pkm.theme")).toBe("dark");

    window.dispatchEvent(
      new CustomEvent("pkm:theme-change", { detail: { theme: "auto" } }),
    );
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(localStorage.getItem("pkm.theme")).toBe("auto");

    unmount(component);
  });

  it("falls back to auto when storage is unavailable", async () => {
    vi.stubGlobal("localStorage", {
      getItem: vi.fn(() => {
        throw new Error("blocked");
      }),
      setItem: vi.fn(() => {
        throw new Error("blocked");
      }),
      clear: vi.fn(),
    });
    const { component } = render();
    await tick();

    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);

    window.dispatchEvent(
      new CustomEvent("pkm:theme-change", { detail: { theme: "light" } }),
    );
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");

    unmount(component);
  });
});
