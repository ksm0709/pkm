// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
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
});
