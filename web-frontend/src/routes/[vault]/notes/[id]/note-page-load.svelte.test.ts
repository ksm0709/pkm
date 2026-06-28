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
    const savedAnnotationBody = JSON.parse(
      mocks.apiClient.mock.calls[0][1].body,
    ).body;
    expect(savedAnnotationBody).toContain("Important context");
    expect(savedAnnotationBody).toContain(
      "([↩ 원문](#quote=quote%20worth%20saving.&occ=0))",
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

  it("scrolls from an annotation source link back to the matching source quote occurrence", async () => {
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
          "Repeat me here.",
          "",
          "Second source says Repeat me here.",
          "",
          "## Annotations",
          "- “Repeat me here.” ([↩ 원문](#quote=Repeat%20me%20here.&occ=1))",
          "  - Source link should target the second source occurrence, not this copied quote.",
        ].join("\n"),
        frontmatter: {},
        created: null,
        updated: null,
        tags: [],
        importance: null,
      };
    });
    const scrollIntoView = vi.fn();
    const originalScrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;

    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(NotePage, { target });

    await waitFor(() => {
      expect(
        target.querySelector<HTMLAnchorElement>('a[href^="#quote="]'),
      ).not.toBeNull();
    });

    target
      .querySelector<HTMLAnchorElement>('a[href^="#quote="]')!
      .dispatchEvent(
        new MouseEvent("click", { bubbles: true, cancelable: true }),
      );
    await tick();

    expect(scrollIntoView).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "center",
    });
    const highlighted = target.querySelector<HTMLElement>(
      ".annotation-source-highlight",
    );
    expect(highlighted?.textContent).toContain(
      "Second source says Repeat me here.",
    );
    expect(highlighted?.textContent).not.toContain("Source link should target");

    Element.prototype.scrollIntoView = originalScrollIntoView;
    unmount(component);
  });

  it("deduplicates nested rendered blocks when resolving annotation source occurrences", async () => {
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
          "> Repeat me here.",
          "",
          "Second source says Repeat me here.",
          "",
          "## Annotations",
          "- “Repeat me here.” ([↩ 원문](#quote=Repeat%20me%20here.&occ=1))",
        ].join("\n"),
        frontmatter: {},
        created: null,
        updated: null,
        tags: [],
        importance: null,
      };
    });
    const scrollIntoView = vi.fn();
    const originalScrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;

    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(NotePage, { target });

    await waitFor(() => {
      expect(
        target.querySelector<HTMLAnchorElement>('a[href^="#quote="]'),
      ).not.toBeNull();
    });
    target
      .querySelector<HTMLAnchorElement>('a[href^="#quote="]')!
      .dispatchEvent(
        new MouseEvent("click", { bubbles: true, cancelable: true }),
      );
    await tick();

    expect(scrollIntoView).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "center",
    });
    expect(
      target.querySelector<HTMLElement>(".annotation-source-highlight")
        ?.textContent,
    ).toContain("Second source says Repeat me here.");

    Element.prototype.scrollIntoView = originalScrollIntoView;
    unmount(component);
  });

  it("keeps parent tight-list text searchable when child list items are also candidates", async () => {
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
          "- Outer quote",
          "  - Inner quote",
          "",
          "## Annotations",
          "- “Outer quote” ([↩ 원문](#quote=Outer%20quote&occ=0))",
        ].join("\n"),
        frontmatter: {},
        created: null,
        updated: null,
        tags: [],
        importance: null,
      };
    });
    const scrollIntoView = vi.fn();
    const originalScrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;

    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(NotePage, { target });

    await waitFor(() => {
      expect(
        target.querySelector<HTMLAnchorElement>('a[href^="#quote="]'),
      ).not.toBeNull();
    });
    target
      .querySelector<HTMLAnchorElement>('a[href^="#quote="]')!
      .dispatchEvent(
        new MouseEvent("click", { bubbles: true, cancelable: true }),
      );
    await tick();

    expect(scrollIntoView).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "center",
    });
    expect(
      target.querySelector<HTMLElement>(".annotation-source-highlight")
        ?.textContent,
    ).toContain("Outer quote");

    Element.prototype.scrollIntoView = originalScrollIntoView;
    unmount(component);
  });

  it("scrolls to a matching source quote when opening the note with a quote hash", async () => {
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
          "First source mentions Anchor me.",
          "",
          "Second source mentions Anchor me.",
          "",
          "## Annotations",
          "- “Anchor me.” ([↩ 원문](#quote=Anchor%20me.&occ=1))",
        ].join("\n"),
        frontmatter: {},
        created: null,
        updated: null,
        tags: [],
        importance: null,
      };
    });
    window.location.hash = "#quote=Anchor%20me.&occ=1";
    const scrollIntoView = vi.fn();
    const originalScrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;

    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(NotePage, { target });

    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalledWith({
        behavior: "smooth",
        block: "center",
      });
    });
    expect(
      target.querySelector<HTMLElement>(".annotation-source-highlight")
        ?.textContent,
    ).toContain("Second source mentions Anchor me.");

    Element.prototype.scrollIntoView = originalScrollIntoView;
    window.location.hash = "";
    unmount(component);
  });

  it("scrolls to an initial quote hash after slow note loading finishes", async () => {
    vi.useFakeTimers();
    mocks.apiGet.mockImplementation(async (path: string) => {
      if (path.endsWith("/neighbors")) {
        return {
          note_id: "alpha-note",
          outbound: [],
          inbound: [],
          semantic: [],
        };
      }
      await new Promise((resolve) => setTimeout(resolve, 1300));
      return {
        note_id: "alpha-note",
        title: "Alpha",
        body: [
          "Slow source mentions Delayed anchor.",
          "",
          "## Annotations",
          "- “Delayed anchor.” ([↩ 원문](#quote=Delayed%20anchor.&occ=0))",
        ].join("\n"),
        frontmatter: {},
        created: null,
        updated: null,
        tags: [],
        importance: null,
      };
    });
    window.location.hash = "#quote=Delayed%20anchor.&occ=0";
    const scrollIntoView = vi.fn();
    const originalScrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;

    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(NotePage, { target });

    await vi.advanceTimersByTimeAsync(1100);
    await flush();
    expect(scrollIntoView).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(250);
    await flush();
    await vi.advanceTimersByTimeAsync(1);
    await flush();

    expect(scrollIntoView).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "center",
    });
    expect(
      target.querySelector<HTMLElement>(".annotation-source-highlight")
        ?.textContent,
    ).toContain("Slow source mentions Delayed anchor.");

    Element.prototype.scrollIntoView = originalScrollIntoView;
    window.location.hash = "";
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

  it("positions the annotate action below the selected text instead of at the pointer", async () => {
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(NotePage, { target });

    await waitFor(() => {
      expect(target.querySelector(".note-body")?.textContent).toContain(
        "Alpha body",
      );
    });

    const noteBody = target.querySelector<HTMLElement>(".note-body");
    const textNode = document
      .createTreeWalker(noteBody!, NodeFilter.SHOW_TEXT)
      .nextNode() as Text;
    const range = document.createRange();
    range.setStart(textNode, 0);
    range.setEnd(textNode, "Alpha body".length);
    range.getBoundingClientRect = () =>
      ({
        x: 100,
        y: 200,
        left: 100,
        top: 200,
        right: 180,
        bottom: 220,
        width: 80,
        height: 20,
        toJSON: () => ({}),
      }) as DOMRect;
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 1000,
    });
    Object.defineProperty(window, "innerHeight", {
      configurable: true,
      value: 800,
    });
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);

    noteBody!.dispatchEvent(
      new MouseEvent("contextmenu", {
        bubbles: true,
        cancelable: true,
        clientX: 12,
        clientY: 34,
      }),
    );
    await tick();

    const menu = target.querySelector<HTMLElement>(".annotate-menu");
    expect(menu?.style.left).toBe("140px");
    expect(menu?.style.top).toBe("230px");

    unmount(component);
  });

  it("dismisses the annotate action when selection collapses, scrolls, or the user clicks outside", async () => {
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(NotePage, { target });

    await waitFor(() => {
      expect(target.querySelector(".note-body")?.textContent).toContain(
        "Alpha body",
      );
    });

    const noteBody = target.querySelector<HTMLElement>(".note-body");
    const textNode = document
      .createTreeWalker(noteBody!, NodeFilter.SHOW_TEXT)
      .nextNode() as Text;
    const openMenu = async () => {
      const range = document.createRange();
      range.setStart(textNode, 0);
      range.setEnd(textNode, "Alpha body".length);
      range.getBoundingClientRect = () =>
        ({
          x: 100,
          y: 200,
          left: 100,
          top: 200,
          right: 180,
          bottom: 220,
          width: 80,
          height: 20,
          toJSON: () => ({}),
        }) as DOMRect;
      window.getSelection()?.removeAllRanges();
      window.getSelection()?.addRange(range);
      noteBody!.dispatchEvent(
        new MouseEvent("contextmenu", {
          bubbles: true,
          cancelable: true,
          clientX: 12,
          clientY: 34,
        }),
      );
      await tick();
      expect(
        target.querySelector('button[aria-label="Annotate selection"]'),
      ).not.toBeNull();
    };

    await openMenu();
    window.getSelection()?.removeAllRanges();
    document.dispatchEvent(new Event("selectionchange"));
    await tick();
    expect(
      target.querySelector('button[aria-label="Annotate selection"]'),
    ).toBeNull();

    await openMenu();
    window.dispatchEvent(new Event("scroll"));
    await tick();
    expect(
      target.querySelector('button[aria-label="Annotate selection"]'),
    ).toBeNull();

    await openMenu();
    document.dispatchEvent(
      new PointerEvent("pointerdown", { bubbles: true, pointerType: "mouse" }),
    );
    await tick();
    expect(
      target.querySelector('button[aria-label="Annotate selection"]'),
    ).toBeNull();

    unmount(component);
  });

  it("cancels a pending touch annotate action when touch scrolling starts", async () => {
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
    window.dispatchEvent(new Event("touchmove"));
    vi.advanceTimersByTime(650);
    await tick();

    expect(
      target.querySelector('button[aria-label="Annotate selection"]'),
    ).toBeNull();

    vi.useRealTimers();
    unmount(component);
  });

  it("marks annotated source blocks persistently and opens the memo popup", async () => {
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
          "A source block contains Marker one.",
          "",
          "## Annotations",
          "- “Marker one.” ([↩ 원문](#quote=Marker%20one.&occ=0))",
          "  - First memo for this source",
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
      const marked = target.querySelector<HTMLElement>(
        ".annotation-source-marked",
      );
      expect(marked).not.toBeNull();
      expect(marked?.textContent).toContain(
        "A source block contains Marker one.",
      );
      expect(marked?.getAttribute("tabindex")).toBe("0");
      expect(marked?.getAttribute("aria-haspopup")).toBe("dialog");
    });

    target
      .querySelector<HTMLElement>(".annotation-source-marked")!
      .dispatchEvent(
        new MouseEvent("click", {
          bubbles: true,
          cancelable: true,
          clientX: 120,
          clientY: 80,
        }),
      );
    await tick();

    const popup = target.querySelector<HTMLElement>(
      '[role="dialog"][aria-label="Annotation memo"]',
    );
    expect(popup?.textContent).toContain("Marker one.");
    expect(popup?.textContent).toContain("First memo for this source");

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await tick();
    expect(
      target.querySelector('[role="dialog"][aria-label="Annotation memo"]'),
    ).toBeNull();

    unmount(component);
  });

  it("shows every annotation memo mapped to the same source block", async () => {
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
          "Shared source sentence has Shared marker.",
          "",
          "## Annotations",
          "- “Shared marker.” ([↩ 원문](#quote=Shared%20marker.&occ=0))",
          "  - First shared memo",
          "- “Shared marker.” ([↩ 원문](#quote=Shared%20marker.&occ=0))",
          "  - Second shared memo",
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
      expect(target.querySelectorAll(".annotation-source-marked")).toHaveLength(
        1,
      );
    });
    target
      .querySelector<HTMLElement>(".annotation-source-marked")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await tick();

    const popupText = target.querySelector<HTMLElement>(
      '[role="dialog"][aria-label="Annotation memo"]',
    )?.textContent;
    expect(popupText).toContain("First shared memo");
    expect(popupText).toContain("Second shared memo");

    unmount(component);
  });

  it("does not mark copied quotes inside the annotation section as source blocks", async () => {
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
          "Only this source has Self copied.",
          "",
          "## Annotations",
          "- “Self copied.” ([↩ 원문](#quote=Self%20copied.&occ=0))",
          "  - The memo repeats Self copied. but should not become a source target.",
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
      const marked = Array.from(
        target.querySelectorAll<HTMLElement>(".annotation-source-marked"),
      );
      expect(marked).toHaveLength(1);
      expect(marked[0].textContent).toContain(
        "Only this source has Self copied.",
      );
      expect(marked[0].textContent).not.toContain("The memo repeats");
    });

    unmount(component);
  });

  it("keeps persistent source marks separate from transient source-link highlights", async () => {
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
          "Persistent source mentions Timer marker.",
          "",
          "## Annotations",
          "- “Timer marker.” ([↩ 원문](#quote=Timer%20marker.&occ=0))",
          "  - Timer memo",
        ].join("\n"),
        frontmatter: {},
        created: null,
        updated: null,
        tags: [],
        importance: null,
      };
    });
    const originalScrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = vi.fn();

    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(NotePage, { target });

    await waitFor(() => {
      expect(target.querySelector(".annotation-source-marked")).not.toBeNull();
    });
    vi.useFakeTimers();
    target
      .querySelector<HTMLAnchorElement>('a[href^="#quote="]')!
      .dispatchEvent(
        new MouseEvent("click", { bubbles: true, cancelable: true }),
      );
    await tick();
    expect(target.querySelector(".annotation-source-highlight")).not.toBeNull();

    await vi.advanceTimersByTimeAsync(2300);
    await flush();

    expect(target.querySelector(".annotation-source-highlight")).toBeNull();
    expect(target.querySelector(".annotation-source-marked")).not.toBeNull();

    Element.prototype.scrollIntoView = originalScrollIntoView;
    vi.useRealTimers();
    unmount(component);
  });

  it("does not open the memo popup when a regular link inside a marked source is clicked", async () => {
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
          "A marked [regular link](https://example.com) source.",
          "",
          "## Annotations",
          "- “regular link” ([↩ 원문](#quote=regular%20link&occ=0))",
          "  - Link memo",
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
        target.querySelector(".annotation-source-marked a"),
      ).not.toBeNull();
    });
    const regularLink = target.querySelector<HTMLAnchorElement>(
      ".annotation-source-marked a",
    )!;
    regularLink.addEventListener("click", (event) => event.preventDefault());
    regularLink.dispatchEvent(
      new MouseEvent("click", { bubbles: true, cancelable: true }),
    );
    await tick();

    expect(
      target.querySelector('[role="dialog"][aria-label="Annotation memo"]'),
    ).toBeNull();

    unmount(component);
  });
});
