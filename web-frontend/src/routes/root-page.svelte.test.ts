// @vitest-environment jsdom
import { goto } from "$app/navigation";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import RootPage from "./+page.svelte";

vi.mock("$app/navigation", () => ({ goto: vi.fn() }));

describe("root page vault routing", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    localStorage.clear();
    sessionStorage.clear();
    document.cookie = "pkm_last_vault=; Max-Age=0; Path=/";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.mocked(goto).mockReset();
    localStorage.clear();
    sessionStorage.clear();
    document.cookie = "pkm_last_vault=; Max-Age=0; Path=/";
    document.body.innerHTML = "";
  });

  async function flush() {
    for (let i = 0; i < 4; i += 1) {
      await Promise.resolve();
      await tick();
    }
  }

  it("reopens the remembered vault before the default vault", async () => {
    localStorage.setItem("pkm.lastVault", "research");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => [
        { name: "main", is_default: true },
        { name: "research" },
      ],
    } as unknown as Response);
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(RootPage, { target });
    await flush();

    expect(goto).toHaveBeenCalledWith("/research/logger");

    unmount(component);
  });

  it("reopens the remembered vault when the vault list is string-shaped", async () => {
    localStorage.setItem("pkm.lastVault", "bear");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => ["@ksm0709--pkm", "bear"],
    } as unknown as Response);
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(RootPage, { target });
    await flush();

    expect(goto).toHaveBeenCalledWith("/bear/logger");

    unmount(component);
  });

  it("reopens the remembered vault from a cookie after process restart", async () => {
    document.cookie = "pkm_last_vault=bear; Path=/";
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => [
        { name: "@ksm0709--pkm", is_default: true },
        { name: "bear" },
      ],
    } as unknown as Response);
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(RootPage, { target });
    await flush();

    expect(goto).toHaveBeenCalledWith("/bear/logger");

    unmount(component);
  });
});
