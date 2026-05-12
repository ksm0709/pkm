// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createRawSnippet, mount, tick, unmount } from "svelte";
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

describe("vault layout window padding", () => {
  let resizeCallback:
    | undefined
    | ((entries: Array<{ contentRect: { width: number } }>) => void);

  beforeEach(() => {
    resizeCallback = undefined;
    mocks.loadConfigs.mockResolvedValue({
      settings: [
        {
          key: "web-window-padding",
          value: "48",
          default_value: "32",
        },
      ],
    });
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(
          callback: (
            entries: Array<{ contentRect: { width: number } }>,
          ) => void,
        ) {
          resizeCallback = callback;
        }
        observe = vi.fn();
        disconnect = vi.fn();
      },
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
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

  it("loads config, measures vault content, handles live config changes, and cleans up", async () => {
    const { component } = render();
    await flush();

    expect(mocks.loadConfigs).toHaveBeenCalledWith("main");
    expect(
      document.documentElement.style.getPropertyValue("--window-padding-raw"),
    ).toBe("48px");

    resizeCallback?.([{ contentRect: { width: 1024 } }]);
    await tick();
    expect(
      document.documentElement.style.getPropertyValue(
        "--vault-content-inline-size",
      ),
    ).toBe("1024px");
    expect(
      document.documentElement.style.getPropertyValue(
        "--content-available-width",
      ),
    ).toContain("var(--vault-content-inline-size)");

    window.dispatchEvent(
      new CustomEvent("pkm:config-change", {
        detail: { key: "web-window-padding", value: "64" },
      }),
    );
    await tick();
    expect(
      document.documentElement.style.getPropertyValue("--window-padding-raw"),
    ).toBe("64px");

    window.dispatchEvent(
      new CustomEvent("pkm:config-change", {
        detail: { key: "model", value: "auto" },
      }),
    );
    await tick();
    expect(
      document.documentElement.style.getPropertyValue("--window-padding-raw"),
    ).toBe("64px");

    unmount(component);
    expect(
      document.documentElement.style.getPropertyValue("--window-padding-raw"),
    ).toBe("");
    expect(
      document.documentElement.style.getPropertyValue(
        "--vault-content-inline-size",
      ),
    ).toBe("");
  });

  it("reloads padding on vault changes and falls back for malformed persisted config", async () => {
    mocks.loadConfigs.mockImplementation(async (vault: string) => ({
      settings: [
        {
          key: "web-window-padding",
          value: vault === "archive" ? "bad-yaml-value" : "40",
          default_value: "32",
        },
      ],
    }));

    const { component } = render();
    await flush();
    expect(
      document.documentElement.style.getPropertyValue("--window-padding-raw"),
    ).toBe("40px");

    mocks.pageStore?.set({
      params: { vault: "archive" },
      url: new URL("http://localhost/archive"),
    });
    await flush();

    expect(mocks.loadConfigs).toHaveBeenCalledWith("archive");
    expect(
      document.documentElement.style.getPropertyValue("--window-padding-raw"),
    ).toBe("32px");

    unmount(component);
  });
});
