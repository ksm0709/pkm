// @vitest-environment jsdom
import { goto } from "$app/navigation";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import Onboarding from "./Onboarding.svelte";

vi.mock("$app/navigation", () => ({ goto: vi.fn() }));

describe("Onboarding", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    localStorage.clear();
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.mocked(goto).mockReset();
    localStorage.clear();
    sessionStorage.clear();
    document.body.innerHTML = "";
  });

  function render() {
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(Onboarding, { target });
    return { target, component };
  }

  async function flush() {
    await Promise.resolve();
    await tick();
  }

  async function submitPassword(target: HTMLElement, password = "secret") {
    const input = target.querySelector<HTMLInputElement>("#password-input")!;
    input.value = password;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await tick();

    target
      .querySelector<HTMLFormElement>("form")!
      .dispatchEvent(
        new SubmitEvent("submit", { bubbles: true, cancelable: true }),
      );
    await flush();
  }

  it("logs in with remembered device payload and returns to the last vault", async () => {
    localStorage.setItem("pkm.lastVault", "research");
    localStorage.setItem("pkm.token", "stale-local");
    sessionStorage.setItem("pkm.token", "stale-session");
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn(),
    } as unknown as Response);
    const { target, component } = render();

    await submitPassword(target);

    expect(fetch).toHaveBeenCalledWith("/api/v1/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: "secret", remember: true }),
    });
    expect(localStorage.getItem("pkm.token")).toBeNull();
    expect(sessionStorage.getItem("pkm.token")).toBeNull();
    expect(goto).toHaveBeenCalledWith("/research/logger");

    unmount(component);
  });

  it("falls back to the first returned vault and sends remember=false when unchecked", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ vaults: [{ name: "main" }, { name: "archive" }] }),
    } as unknown as Response);
    const { target, component } = render();

    target.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click();
    await tick();
    await submitPassword(target, "one-shot");

    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body))).toEqual(
      {
        password: "one-shot",
        remember: false,
      },
    );
    expect(goto).toHaveBeenCalledWith("/main/logger");

    unmount(component);
  });

  it("shows an invalid-password alert without navigating on 401", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 401,
    } as Response);
    const { target, component } = render();

    await submitPassword(target, "wrong");

    expect(target.querySelector('[role="alert"]')?.textContent).toBe(
      "Invalid password.",
    );
    expect(goto).not.toHaveBeenCalled();

    unmount(component);
  });

  it("shows a daemon connectivity alert when login cannot reach the backend", async () => {
    vi.mocked(fetch).mockRejectedValue(new Error("offline"));
    const { target, component } = render();

    await submitPassword(target);

    expect(target.querySelector('[role="alert"]')?.textContent).toBe(
      "Cannot reach daemon. Is pkm running?",
    );
    expect(goto).not.toHaveBeenCalled();

    unmount(component);
  });
});
