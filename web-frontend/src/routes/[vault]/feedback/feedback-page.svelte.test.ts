// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { apiClient, apiGet } from "$lib/api/client.js";
import Page from "./+page.svelte";

vi.mock("$app/stores", async () => {
  const { readable } = await import("svelte/store");
  return { page: readable({ params: { vault: "main" } }) };
});
vi.mock("$lib/api/client.js", () => ({ apiClient: vi.fn(), apiGet: vi.fn() }));

describe("feedback page", () => {
  beforeEach(() => {
    vi.mocked(apiGet).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.mocked(apiClient).mockReset();
    vi.mocked(apiGet).mockReset();
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
    return { target, component: mount(Page, { target }) };
  }

  it("loads the vault feedback ledger", async () => {
    vi.mocked(apiGet).mockResolvedValue([
      {
        note_id: "2026-08-15-feedback-offline-feedback",
        title: "Keep feedback local",
        description: "Do not require a GitHub account.",
        feedback_type: "requirement",
        created_at: "2026-08-15T09:30:00Z",
      },
    ]);
    const { target, component } = render();
    await flush();

    expect(apiGet).toHaveBeenCalledWith("/api/v1/vault/main/feedback");
    expect(target.textContent).toContain("Keep feedback local");
    expect(target.textContent).toContain("Do not require a GitHub account.");

    unmount(component);
  });

  it("saves feedback and immediately adds it to the ledger", async () => {
    vi.mocked(apiClient).mockResolvedValue(
      new Response(
        JSON.stringify({
          note_id: "2026-08-15-feedback-offline-feedback",
          title: "Keep feedback local",
          description: "Do not require a GitHub account.",
          feedback_type: "requirement",
          created_at: "2026-08-15T09:30:00Z",
        }),
        { status: 201 },
      ),
    );
    const { target, component } = render();
    await flush();

    const inputs = target.querySelectorAll<HTMLInputElement>("input");
    const title = Array.from(inputs).find((input) => input.type === "text");
    const description = target.querySelector<HTMLTextAreaElement>("textarea");
    title!.value = "Keep feedback local";
    title!.dispatchEvent(new Event("input", { bubbles: true }));
    description!.value = "Do not require a GitHub account.";
    description!.dispatchEvent(new Event("input", { bubbles: true }));
    target
      .querySelector<HTMLFormElement>("form")
      ?.dispatchEvent(
        new SubmitEvent("submit", { bubbles: true, cancelable: true }),
      );
    await flush();

    expect(apiClient).toHaveBeenCalledWith("/api/v1/vault/main/feedback", {
      method: "POST",
      body: JSON.stringify({
        title: "Keep feedback local",
        description: "Do not require a GitHub account.",
        feedback_type: "requirement",
      }),
    });
    expect(target.textContent).toContain("Saved to this vault");
    expect(target.textContent).toContain("Keep feedback local");

    unmount(component);
  });
});
