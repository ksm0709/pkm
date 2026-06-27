// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { graphKeyNav } from "$lib/navigation/graph-keynav.svelte";
import NotePage from "./+page.svelte";

const mocks = vi.hoisted(() => ({
  apiClient: vi.fn(),
  apiGet: vi.fn(),
  pageStore: undefined as
    | undefined
    | {
        set: (value: {
          params: { vault: string; id: string };
          url: URL;
        }) => void;
        subscribe: (run: (value: unknown) => void) => () => void;
      },
}));

const mermaidMock = vi.hoisted(() => ({
  initialize: vi.fn(),
  render: vi.fn(async (_id: string, source: string) => ({
    svg: `<svg><text>${source}</text></svg>`,
  })),
}));

vi.mock("$lib/api/client.js", () => ({
  apiClient: mocks.apiClient,
  apiGet: mocks.apiGet,
}));

vi.mock("$app/stores", async () => {
  const { writable } = await import("svelte/store");
  mocks.pageStore = writable({
    params: { vault: "main", id: "alpha-note" },
    url: new URL("http://localhost/main/notes/alpha-note"),
  });
  return {
    page: { subscribe: mocks.pageStore.subscribe },
  };
});

vi.mock(
  "mermaid",
  () => ({
    default: mermaidMock,
  }),
  { virtual: true },
);

describe("note page loading", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    document.body.innerHTML = "";
    graphKeyNav.resetForTests();
    mocks.pageStore?.set({
      params: { vault: "main", id: "alpha-note" },
      url: new URL("http://localhost/main/notes/alpha-note"),
    });
    vi.stubGlobal("localStorage", {
      setItem: vi.fn(),
      getItem: vi.fn(),
      removeItem: vi.fn(),
    });
    mocks.apiGet.mockImplementation(async (path: string) => {
      if (path.includes("/graph/ego/")) {
        return { center: "alpha-note", nodes: [], links: [] };
      }
      if (path.endsWith("/neighbors")) {
        return {
          note_id: "alpha-note",
          outbound: [],
          inbound: [],
          semantic: [{ note_id: "beta-note", title: "Beta", confidence: 0.91 }],
        };
      }
      return {
        note_id: "alpha-note",
        title: "Alpha",
        body: "Alpha body",
        frontmatter: {},
        created: null,
        updated: null,
        tags: [],
        importance: null,
      };
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    window.getSelection()?.removeAllRanges();
  });

  async function flush() {
    for (let i = 0; i < 8; i += 1) {
      await Promise.resolve();
      await tick();
    }
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

  it("does not reload the note when graph navigation context is published", async () => {
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(NotePage, { target });
    await flush();

    const paths = mocks.apiGet.mock.calls.map(([path]) => path);
    expect(
      paths.filter((path) => path === "/api/v1/vault/main/notes/alpha-note"),
    ).toHaveLength(1);
    expect(
      paths.filter(
        (path) => path === "/api/v1/vault/main/notes/alpha-note/neighbors",
      ),
    ).toHaveLength(1);

    unmount(component);
  });

  it("renders note bodies through the sanitized markdown renderer", async () => {
    mocks.apiGet.mockImplementation(async (path: string) => {
      if (path.endsWith("/neighbors")) {
        return {
          note_id: "alpha-note",
          outbound: [],
          inbound: [],
          semantic: [],
        };
      }
      return {
        note_id: "alpha-note",
        title: "Alpha",
        body: [
          '<svg viewBox="0 0 10 10" aria-label="diagram" onload="alert(1)">',
          '<path d="M1 1h8v8H1z" fill="currentColor"></path>',
          "<script>alert('xss')</script>",
          "</svg>",
          "",
          "- [ ] task stays interactive",
          "",
          "```mermaid",
          "graph TD",
          "  A --> B",
          "```",
        ].join("\n"),
        frontmatter: {},
        created: null,
        updated: null,
        tags: [],
        importance: null,
      };
    });

    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(NotePage, { target });
    await waitFor(() => {
      expect(
        target.querySelector(".note-body svg[aria-label='diagram'] path"),
      ).not.toBeNull();
      expect(
        target.querySelector(".note-body .mermaid-rendered svg"),
      ).not.toBeNull();
    });

    expect(
      target.querySelector(".note-body script, .note-body [onload]"),
    ).toBeNull();
    const taskButton = target.querySelector<HTMLButtonElement>(
      "button.note-task-state",
    );
    expect(taskButton?.dataset.taskState).toBe("[ ]");
    expect(taskButton?.getAttribute("aria-label")).toBe("Task status todo");
    expect(mermaidMock.render).toHaveBeenCalledWith(
      expect.stringMatching(/^pkm-mermaid-/),
      expect.stringContaining("graph TD"),
    );

    unmount(component);
  });

  it("annotates the selected note text and optionally adds a daily log entry", async () => {
    mocks.apiGet.mockImplementation(async (path: string) => {
      if (path.endsWith("/neighbors")) {
        return {
          note_id: "alpha-note",
          outbound: [],
          inbound: [],
          semantic: [],
        };
      }
      return {
        note_id: "alpha-note",
        title: "Alpha",
        body: "Alpha body has a quote worth saving.",
        frontmatter: {},
        created: null,
        updated: null,
        tags: [],
        importance: null,
      };
    });
    mocks.apiClient
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            note_id: "alpha-note",
            title: "Alpha",
            body: [
              "Alpha body has a quote worth saving.",
              "",
              "## Annotations",
              "",
              "- “quote worth saving.”",
              "  - Important context",
            ].join("\n"),
            frontmatter: {},
            created: null,
            updated: null,
            tags: [],
            importance: null,
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            entry:
              "- [10:15:00] Annotated [[alpha-note]]: “quote worth saving.” — Important context",
          }),
          { status: 201 },
        ),
      );

    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(NotePage, { target });
    await waitFor(() => {
      expect(target.querySelector(".note-body")?.textContent).toContain(
        "quote worth saving",
      );
    });

    const noteBody = target.querySelector<HTMLElement>(".note-body");
    expect(noteBody).not.toBeNull();
    const textNode = document
      .createTreeWalker(noteBody!, NodeFilter.SHOW_TEXT)
      .nextNode() as Text;
    const start = textNode.data.indexOf("quote worth saving");
    expect(start).toBeGreaterThanOrEqual(0);
    const range = document.createRange();
    range.setStart(textNode, start);
    range.setEnd(textNode, start + "quote worth saving.".length);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);

    noteBody!.dispatchEvent(
      new MouseEvent("contextmenu", {
        bubbles: true,
        cancelable: true,
        clientX: 42,
        clientY: 84,
      }),
    );
    await tick();

    const annotateButton = target.querySelector<HTMLButtonElement>(
      'button[aria-label="Annotate selection"]',
    );
    expect(annotateButton?.textContent).toContain("Annotate");
    annotateButton?.click();
    await tick();

    const textarea = target.querySelector<HTMLTextAreaElement>(
      'textarea[aria-label="Annotation text"]',
    );
    expect(textarea).not.toBeNull();
    textarea!.value = "Important context";
    textarea!.dispatchEvent(new Event("input", { bubbles: true }));

    const addToLog = target.querySelector<HTMLInputElement>(
      'input[aria-label="Add annotation to daily log"]',
    );
    expect(addToLog).not.toBeNull();
    addToLog!.checked = true;
    addToLog!.dispatchEvent(new Event("change", { bubbles: true }));

    target
      .querySelector<HTMLButtonElement>('button[aria-label="Save annotation"]')
      ?.click();
    await flush();

    expect(mocks.apiClient).toHaveBeenNthCalledWith(
      1,
      "/api/v1/vault/main/notes/alpha-note",
      {
        method: "PUT",
        body: expect.stringContaining("## Annotations"),
      },
    );
    expect(JSON.parse(mocks.apiClient.mock.calls[0][1].body).body).toContain(
      "Important context",
    );
    expect(mocks.apiClient).toHaveBeenNthCalledWith(
      2,
      "/api/v1/vault/main/daily/today",
      {
        method: "POST",
        body: JSON.stringify({
          type: "entry",
          content:
            "Annotated [[alpha-note]]: “quote worth saving.” — Important context",
        }),
      },
    );
    expect(target.querySelector('[role="dialog"]')).toBeNull();

    unmount(component);
  });

  it("opens the annotate action from a long press on selected note text", async () => {
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(NotePage, { target });
    await waitFor(() => {
      expect(target.querySelector(".note-body")?.textContent).toContain(
        "Alpha body",
      );
    });

    vi.useFakeTimers();
    const noteBody = target.querySelector<HTMLElement>(".note-body");
    const textNode = document
      .createTreeWalker(noteBody!, NodeFilter.SHOW_TEXT)
      .nextNode() as Text;
    const range = document.createRange();
    range.setStart(textNode, 0);
    range.setEnd(textNode, "Alpha body".length);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);

    noteBody!.dispatchEvent(
      new PointerEvent("pointerdown", {
        bubbles: true,
        pointerType: "touch",
        clientX: 24,
        clientY: 48,
      }),
    );
    vi.advanceTimersByTime(650);
    await tick();

    expect(
      target.querySelector<HTMLButtonElement>(
        'button[aria-label="Annotate selection"]',
      )?.textContent,
    ).toContain("Annotate");

    vi.useRealTimers();
    unmount(component);
  });

  it("does not duplicate the annotation when retrying after daily log failure", async () => {
    mocks.apiGet.mockImplementation(async (path: string) => {
      if (path.endsWith("/neighbors")) {
        return {
          note_id: "alpha-note",
          outbound: [],
          inbound: [],
          semantic: [],
        };
      }
      return {
        note_id: "alpha-note",
        title: "Alpha",
        body: "Alpha body has a quote worth saving.",
        frontmatter: {},
        created: null,
        updated: null,
        tags: [],
        importance: null,
      };
    });
    const annotatedBody = [
      "Alpha body has a quote worth saving.",
      "",
      "## Annotations",
      "- “quote worth saving.”",
      "  - Important context",
      "",
    ].join("\n");
    mocks.apiClient
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            note_id: "alpha-note",
            title: "Alpha",
            body: annotatedBody,
            frontmatter: {},
            created: null,
            updated: null,
            tags: [],
            importance: null,
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(new Response("", { status: 500 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            note_id: "alpha-note",
            title: "Alpha",
            body: annotatedBody,
            frontmatter: {},
            created: null,
            updated: null,
            tags: [],
            importance: null,
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ entry: "- [10:15:00] logged" }), {
          status: 201,
        }),
      );

    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(NotePage, { target });

    await waitFor(() => {
      expect(target.querySelector(".note-body")?.textContent).toContain(
        "quote worth saving",
      );
    });

    const noteBody = target.querySelector<HTMLElement>(".note-body");
    const textNode = document
      .createTreeWalker(noteBody!, NodeFilter.SHOW_TEXT)
      .nextNode() as Text;
    const start = textNode.data.indexOf("quote worth saving");
    const range = document.createRange();
    range.setStart(textNode, start);
    range.setEnd(textNode, start + "quote worth saving.".length);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);

    noteBody!.dispatchEvent(
      new MouseEvent("contextmenu", {
        bubbles: true,
        cancelable: true,
        clientX: 42,
        clientY: 84,
      }),
    );
    await tick();
    target
      .querySelector<HTMLButtonElement>(
        'button[aria-label="Annotate selection"]',
      )
      ?.click();
    await tick();

    const textarea = target.querySelector<HTMLTextAreaElement>(
      'textarea[aria-label="Annotation text"]',
    );
    textarea!.value = "Important context";
    textarea!.dispatchEvent(new Event("input", { bubbles: true }));
    const addToLog = target.querySelector<HTMLInputElement>(
      'input[aria-label="Add annotation to daily log"]',
    );
    addToLog!.checked = true;
    addToLog!.dispatchEvent(new Event("change", { bubbles: true }));

    target
      .querySelector<HTMLButtonElement>('button[aria-label="Save annotation"]')
      ?.click();
    await flush();
    expect(target.querySelector('[role="dialog"]')).not.toBeNull();
    expect(target.querySelector(".annotate-error")?.textContent).toContain(
      "POST daily log",
    );

    target
      .querySelector<HTMLButtonElement>('button[aria-label="Save annotation"]')
      ?.click();
    await flush();

    const secondPutBody = JSON.parse(
      mocks.apiClient.mock.calls[2][1].body,
    ).body;
    expect(secondPutBody.match(/Important context/g)).toHaveLength(1);
    expect(target.querySelector('[role="dialog"]')).toBeNull();

    unmount(component);
  });

  it("does not apply a completed annotation save to a different note route", async () => {
    mocks.apiGet.mockImplementation(async (path: string) => {
      if (path.endsWith("/neighbors")) {
        const note_id = path.includes("beta-note") ? "beta-note" : "alpha-note";
        return { note_id, outbound: [], inbound: [], semantic: [] };
      }
      if (path.endsWith("/notes/beta-note")) {
        return {
          note_id: "beta-note",
          title: "Beta",
          body: "Beta body",
          frontmatter: {},
          created: null,
          updated: null,
          tags: [],
          importance: null,
        };
      }
      return {
        note_id: "alpha-note",
        title: "Alpha",
        body: "Alpha body has a quote worth saving.",
        frontmatter: {},
        created: null,
        updated: null,
        tags: [],
        importance: null,
      };
    });

    let resolveSave: ((response: Response) => void) | undefined;
    mocks.apiClient.mockReturnValueOnce(
      new Promise<Response>((resolve) => {
        resolveSave = resolve;
      }),
    );

    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(NotePage, { target });

    await waitFor(() => {
      expect(target.querySelector(".note-body")?.textContent).toContain(
        "quote worth saving",
      );
    });

    const noteBody = target.querySelector<HTMLElement>(".note-body");
    const textNode = document
      .createTreeWalker(noteBody!, NodeFilter.SHOW_TEXT)
      .nextNode() as Text;
    const start = textNode.data.indexOf("quote worth saving");
    const range = document.createRange();
    range.setStart(textNode, start);
    range.setEnd(textNode, start + "quote worth saving.".length);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);

    noteBody!.dispatchEvent(
      new MouseEvent("contextmenu", {
        bubbles: true,
        cancelable: true,
        clientX: 42,
        clientY: 84,
      }),
    );
    await tick();
    target
      .querySelector<HTMLButtonElement>(
        'button[aria-label="Annotate selection"]',
      )
      ?.click();
    await tick();

    const textarea = target.querySelector<HTMLTextAreaElement>(
      'textarea[aria-label="Annotation text"]',
    );
    textarea!.value = "Important context";
    textarea!.dispatchEvent(new Event("input", { bubbles: true }));
    target
      .querySelector<HTMLButtonElement>('button[aria-label="Save annotation"]')
      ?.click();
    await tick();

    mocks.pageStore?.set({
      params: { vault: "main", id: "beta-note" },
      url: new URL("http://localhost/main/notes/beta-note"),
    });
    await flush();

    resolveSave?.(
      new Response(
        JSON.stringify({
          note_id: "alpha-note",
          title: "Alpha",
          body: "Alpha body has a quote worth saving.\n\n## Annotations\n- “quote worth saving.”\n  - Important context\n",
          frontmatter: {},
          created: null,
          updated: null,
          tags: [],
          importance: null,
        }),
        { status: 200 },
      ),
    );
    await flush();

    expect(target.querySelector(".note-body")?.textContent).toContain(
      "Beta body",
    );
    expect(target.querySelector(".note-body")?.textContent).not.toContain(
      "Important context",
    );

    unmount(component);
  });

  it("clears an in-progress annotation when navigating to another note", async () => {
    mocks.apiGet.mockImplementation(async (path: string) => {
      if (path.endsWith("/neighbors")) {
        const note_id = path.includes("beta-note") ? "beta-note" : "alpha-note";
        return { note_id, outbound: [], inbound: [], semantic: [] };
      }
      if (path.endsWith("/notes/beta-note")) {
        return {
          note_id: "beta-note",
          title: "Beta",
          body: "Beta body",
          frontmatter: {},
          created: null,
          updated: null,
          tags: [],
          importance: null,
        };
      }
      return {
        note_id: "alpha-note",
        title: "Alpha",
        body: "Alpha body has a quote worth saving.",
        frontmatter: {},
        created: null,
        updated: null,
        tags: [],
        importance: null,
      };
    });

    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(NotePage, { target });

    await waitFor(() => {
      expect(target.querySelector(".note-body")?.textContent).toContain(
        "quote worth saving",
      );
    });

    const noteBody = target.querySelector<HTMLElement>(".note-body");
    const textNode = document
      .createTreeWalker(noteBody!, NodeFilter.SHOW_TEXT)
      .nextNode() as Text;
    const start = textNode.data.indexOf("quote worth saving");
    const range = document.createRange();
    range.setStart(textNode, start);
    range.setEnd(textNode, start + "quote worth saving.".length);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);

    noteBody!.dispatchEvent(
      new MouseEvent("contextmenu", {
        bubbles: true,
        cancelable: true,
        clientX: 42,
        clientY: 84,
      }),
    );
    await tick();
    target
      .querySelector<HTMLButtonElement>(
        'button[aria-label="Annotate selection"]',
      )
      ?.click();
    await tick();
    expect(target.querySelector('[role="dialog"]')).not.toBeNull();

    mocks.pageStore?.set({
      params: { vault: "main", id: "beta-note" },
      url: new URL("http://localhost/main/notes/beta-note"),
    });
    await flush();

    expect(target.querySelector(".note-body")?.textContent).toContain(
      "Beta body",
    );
    expect(target.querySelector('[role="dialog"]')).toBeNull();
    expect(
      target.querySelector('button[aria-label="Annotate selection"]'),
    ).toBeNull();

    unmount(component);
  });
});
