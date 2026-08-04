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
    await waitFor(() => {
      expect(goto).toHaveBeenCalledWith(
        "/main/notes/2026-05-12-research-notes",
      );
    });

    expect(prompt).toHaveBeenCalledWith("Subnote title");
    expect(apiClient).toHaveBeenCalledWith("/api/v1/vault/main/daily/today", {
      method: "POST",
      body: JSON.stringify({
        type: "subnote",
        title: "research notes",
        content: "",
      }),
    });
    expect(target.querySelector('[role="menu"]')).toBeNull();

    unmount(component);
  });

  it("creates a general note from the logger action menu and opens it", async () => {
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "research notes"),
    );
    vi.mocked(apiClient).mockResolvedValue(
      new Response(JSON.stringify({ note_id: "research-notes" }), {
        status: 201,
      }),
    );
    const { target, component } = render();
    await flush();

    target
      .querySelector<HTMLButtonElement>(
        'button[aria-label="Open logger actions"]',
      )
      ?.click();
    await tick();

    const addNote = target.querySelector<HTMLButtonElement>(
      'button[aria-label="Add note"]',
    );
    expect(addNote).not.toBeNull();
    addNote?.click();

    await waitFor(() => {
      expect(apiClient).toHaveBeenCalledWith("/api/v1/vault/main/notes", {
        method: "POST",
        body: JSON.stringify({
          title: "research notes",
          body: "",
          tags: [],
        }),
      });
    });
    await waitFor(() => {
      expect(goto).toHaveBeenCalledWith("/main/notes/research-notes");
    });

    unmount(component);
  });

  it("does not call the API when a general note title is cancelled, empty, or whitespace", async () => {
    vi.stubGlobal(
      "prompt",
      vi
        .fn()
        .mockReturnValueOnce(null)
        .mockReturnValueOnce("")
        .mockReturnValueOnce("   "),
    );
    const { target, component } = render();
    await flush();

    for (let i = 0; i < 3; i += 1) {
      target
        .querySelector<HTMLButtonElement>(
          'button[aria-label="Open logger actions"]',
        )
        ?.click();
      await tick();
      target
        .querySelector<HTMLButtonElement>('button[aria-label="Add note"]')
        ?.click();
      await flush();
    }

    expect(prompt).toHaveBeenCalledTimes(3);
    expect(apiClient).not.toHaveBeenCalled();

    unmount(component);
  });

  it("shows a rejected general note create request error and clears the busy state", async () => {
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "research notes"),
    );
    vi.mocked(apiClient).mockRejectedValue(new Error("network unavailable"));
    const { target, component } = render();
    await flush();

    const actionsButton = target.querySelector<HTMLButtonElement>(
      'button[aria-label="Open logger actions"]',
    );
    actionsButton?.click();
    await tick();
    target
      .querySelector<HTMLButtonElement>('button[aria-label="Add note"]')
      ?.click();

    await waitFor(() => {
      expect(target.querySelector(".status.error")?.textContent).toContain(
        "network unavailable",
      );
    });
    expect(actionsButton?.disabled).toBe(false);

    unmount(component);
  });

  it("does not prompt or post again while a general note creation request is pending", async () => {
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "research notes"),
    );
    vi.mocked(apiClient).mockReturnValueOnce(new Promise(() => {}));
    const { target, component } = render();
    await flush();

    const actionsButton = target.querySelector<HTMLButtonElement>(
      'button[aria-label="Open logger actions"]',
    );
    actionsButton?.click();
    await tick();
    target
      .querySelector<HTMLButtonElement>('button[aria-label="Add note"]')
      ?.click();
    await waitFor(() => {
      expect(apiClient).toHaveBeenCalledTimes(1);
    });

    actionsButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await tick();
    target
      .querySelector<HTMLButtonElement>('button[aria-label="Add note"]')
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flush();

    expect(prompt).toHaveBeenCalledTimes(1);
    expect(apiClient).toHaveBeenCalledTimes(1);

    unmount(component);
  });

  it("shows a visible error when a new note response omits note_id", async () => {
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "research notes"),
    );
    vi.mocked(apiClient).mockResolvedValue(
      new Response(JSON.stringify({}), { status: 201 }),
    );
    const { target, component } = render();
    await flush();

    target
      .querySelector<HTMLButtonElement>(
        'button[aria-label="Open logger actions"]',
      )
      ?.click();
    await tick();
    target
      .querySelector<HTMLButtonElement>('button[aria-label="Add note"]')
      ?.click();

    await waitFor(() => {
      expect(target.querySelector(".error")?.textContent).toContain(
        "POST note -> missing note_id",
      );
    });
    expect(goto).not.toHaveBeenCalled();

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
    await waitFor(() => {
      expect(apiClient).toHaveBeenCalledTimes(2);
    });

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
    await waitFor(() => {
      expect(textarea?.value).toContain(
        "See [report.pdf](/api/v1/vault/main/data/report.pdf)",
      );
    });

    expect(apiClient).toHaveBeenCalledTimes(1);

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
