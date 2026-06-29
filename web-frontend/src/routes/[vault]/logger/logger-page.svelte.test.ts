// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { goto } from "$app/navigation";
import { mount, tick, unmount } from "svelte";
import { apiClient, apiGet } from "$lib/api/client.js";
import Page from "./+page.svelte";

vi.mock("$app/navigation", () => ({ goto: vi.fn() }));
vi.mock("$app/stores", async () => {
  const { readable } = await import("svelte/store");
  return {
    page: readable({ params: { vault: "main" } }),
  };
});
vi.mock("$lib/api/client.js", () => ({
  apiClient: vi.fn(),
  apiGet: vi.fn(),
}));

describe("logger page", () => {
  beforeEach(() => {
    vi.mocked(apiGet).mockResolvedValue({
      note_id: "2026-05-12",
      title: "2026-05-12",
      body: "## Logs\n- [09:00:00] Started logging",
    });
  });

  afterEach(() => {
    vi.mocked(apiClient).mockReset();
    vi.mocked(apiGet).mockReset();
    vi.mocked(goto).mockReset();
    vi.unstubAllGlobals();
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
    const component = mount(Page, { target });
    return { target, component };
  }

  async function waitFor(assertion: () => void | Promise<void>) {
    let lastError: unknown;
    for (let i = 0; i < 30; i += 1) {
      try {
        await assertion();
        return;
      } catch (error) {
        lastError = error;
        await Promise.resolve();
        await new Promise((resolve) => setTimeout(resolve, 0));
        await tick();
      }
    }
    throw lastError;
  }

  it("opens logger actions from the plus button and creates a daily sub-note", async () => {
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "research notes"),
    );
    vi.mocked(apiClient).mockResolvedValue(
      new Response(JSON.stringify({ note_id: "2026-05-12-research-notes" }), {
        status: 201,
      }),
    );
    const { target, component } = render();
    await flush();

    const actionsButton = target.querySelector<HTMLButtonElement>(
      'button[aria-label="Open logger actions"]',
    );
    expect(actionsButton).not.toBeNull();
    actionsButton?.click();
    await tick();

    const subnoteAction = target.querySelector<HTMLButtonElement>(
      'button[aria-label="Add sub-note"]',
    );
    expect(subnoteAction?.textContent).toContain("Add sub-note");
    subnoteAction?.click();
    await flush();

    expect(prompt).toHaveBeenCalledWith("Subnote title");
    expect(apiClient).toHaveBeenCalledWith("/api/v1/vault/main/daily/today", {
      method: "POST",
      body: JSON.stringify({
        type: "subnote",
        title: "research notes",
        content: "",
      }),
    });
    expect(goto).toHaveBeenCalledWith("/main/notes/2026-05-12-research-notes");
    expect(target.querySelector('[role="menu"]')).toBeNull();

    unmount(component);
  });

  it("uploads a selected file from the logger action menu and creates a visible log entry", async () => {
    vi.mocked(apiClient)
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            filename: "report.pdf",
            href: "/api/v1/vault/main/data/report.pdf",
            markdown: "[report.pdf](/api/v1/vault/main/data/report.pdf)",
            size: 12,
            content_type: "application/pdf",
          }),
          { status: 201 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            entry:
              "- [10:15:00] [report.pdf](/api/v1/vault/main/data/report.pdf)",
          }),
          { status: 201 },
        ),
      );
    const { target, component } = render();
    await flush();

    target
      .querySelector<HTMLButtonElement>(
        'button[aria-label="Open logger actions"]',
      )
      ?.click();
    await tick();

    const uploadAction = target.querySelector<HTMLButtonElement>(
      'button[aria-label="Upload file"]',
    );
    expect(uploadAction?.textContent).toContain("Upload file");
    uploadAction?.click();
    await tick();

    const fileInput = target.querySelector<HTMLInputElement>(
      'input[type="file"][aria-label="Upload file"]',
    );
    expect(fileInput).not.toBeNull();
    const file = new File(["pdf content"], "report.pdf", {
      type: "application/pdf",
    });
    Object.defineProperty(fileInput, "files", {
      configurable: true,
      value: [file],
    });
    fileInput?.dispatchEvent(new Event("change", { bubbles: true }));
    await flush();

    expect(apiClient).toHaveBeenNthCalledWith(1, "/api/v1/vault/main/data", {
      method: "POST",
      body: expect.any(FormData),
    });
    expect(apiClient).toHaveBeenNthCalledWith(
      2,
      "/api/v1/vault/main/daily/today",
      {
        method: "POST",
        body: JSON.stringify({
          type: "entry",
          content: "[report.pdf](/api/v1/vault/main/data/report.pdf)",
        }),
      },
    );
    await waitFor(() => {
      expect(
        target.querySelector<HTMLAnchorElement>(
          'a[href="/main/view-data/report.pdf"]',
        )?.textContent,
      ).toBe("report.pdf");
    });
    expect(
      target.querySelector<HTMLTextAreaElement>(".logger-textarea")?.value,
    ).toBe("");
    expect(target.querySelector('[role="menu"]')).toBeNull();

    unmount(component);
  });

  it("inserts uploaded markdown into an in-progress logger draft", async () => {
    vi.mocked(apiClient).mockResolvedValue(
      new Response(
        JSON.stringify({
          filename: "report.pdf",
          href: "/api/v1/vault/main/data/report.pdf",
          markdown: "[report.pdf](/api/v1/vault/main/data/report.pdf)",
          size: 12,
          content_type: "application/pdf",
        }),
        { status: 201 },
      ),
    );
    const { target, component } = render();
    await flush();

    const textarea =
      target.querySelector<HTMLTextAreaElement>(".logger-textarea");
    expect(textarea).not.toBeNull();
    textarea!.value = "See";
    textarea!.setSelectionRange(3, 3);
    textarea!.dispatchEvent(new Event("input", { bubbles: true }));

    target
      .querySelector<HTMLButtonElement>(
        'button[aria-label="Open logger actions"]',
      )
      ?.click();
    await tick();
    target
      .querySelector<HTMLButtonElement>('button[aria-label="Upload file"]')
      ?.click();
    await tick();

    const fileInput = target.querySelector<HTMLInputElement>(
      'input[type="file"][aria-label="Upload file"]',
    );
    Object.defineProperty(fileInput, "files", {
      configurable: true,
      value: [
        new File(["pdf content"], "report.pdf", {
          type: "application/pdf",
        }),
      ],
    });
    fileInput?.dispatchEvent(new Event("change", { bubbles: true }));
    await flush();

    expect(apiClient).toHaveBeenCalledTimes(1);
    expect(textarea?.value).toContain(
      "See [report.pdf](/api/v1/vault/main/data/report.pdf)",
    );

    unmount(component);
  });

  it("renders markdown and wikilinks in saved log entries", async () => {
    vi.mocked(apiGet).mockResolvedValue({
      note_id: "2026-05-12",
      title: "2026-05-12",
      body: "## Logs\n- [09:00:00] See **bold** [[Target Note]] #pkm",
    });
    const { target, component } = render();

    await waitFor(() => {
      expect(target.querySelector("strong")?.textContent).toBe("bold");
    });

    expect(
      target.querySelector<HTMLAnchorElement>(
        'a[href="/main/notes/Target%20Note"]',
      )?.textContent,
    ).toBe("Target Note");
    expect(target.querySelector(".note-tag-chip")?.textContent).toBe("#pkm");

    unmount(component);
  });
});
