// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { goto } from "$app/navigation";
import Topbar from "./Topbar.svelte";

vi.mock("$app/navigation", () => ({ goto: vi.fn() }));

describe("Topbar", () => {
  afterEach(() => {
    vi.mocked(goto).mockReset();
    document.body.innerHTML = "";
  });

  it("renders the vault breadcrumb and routes it to the vault logger", async () => {
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(Topbar, {
      target,
      props: {
        vaultName: "work vault",
        pageName: "notes",
      },
    });
    await tick();

    expect(target.querySelector("header")?.getAttribute("aria-label")).toBe(
      "Vault status rail",
    );
    expect(target.querySelector(".vault-name")?.textContent).toBe("work vault");
    expect(target.querySelector(".page-name")?.textContent).toBe("notes");

    target.querySelector<HTMLButtonElement>(".breadcrumb")?.click();
    expect(goto).toHaveBeenCalledWith("/work vault/logger");

    unmount(component);
  });

  it("disables logger routing when no vault is selected", async () => {
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(Topbar, { target, props: { pageName: "home" } });
    await tick();

    const breadcrumb = target.querySelector<HTMLButtonElement>(".breadcrumb");
    expect(breadcrumb?.disabled).toBe(true);
    expect(target.querySelector(".vault-name")?.textContent).toBe("pkm");

    breadcrumb?.click();
    expect(goto).not.toHaveBeenCalled();

    unmount(component);
  });

  it("exposes drawer and command palette controls as callbacks with stateful labels", async () => {
    const target = document.createElement("div");
    const toggleDrawer = vi.fn();
    const openCommandPalette = vi.fn();
    document.body.appendChild(target);

    const component = mount(Topbar, {
      target,
      props: {
        vaultName: "main",
        pageName: "graph",
        drawerOpen: true,
        toggleDrawer,
        openCommandPalette,
      },
    });
    await tick();

    const drawerButton =
      target.querySelector<HTMLButtonElement>(".drawer-toggle");
    expect(drawerButton?.getAttribute("aria-label")).toBe(
      "Close navigation drawer",
    );
    expect(drawerButton?.getAttribute("aria-pressed")).toBe("true");

    drawerButton?.click();
    target.querySelector<HTMLButtonElement>(".command-button")?.click();

    expect(toggleDrawer).toHaveBeenCalledTimes(1);
    expect(openCommandPalette).toHaveBeenCalledTimes(1);

    unmount(component);
  });
});
