// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { goto } from "$app/navigation";
import { apiGet } from "$lib/api/client.js";
import NeighborPanel from "./NeighborPanel.svelte";

vi.mock("$app/navigation", () => ({ goto: vi.fn() }));
vi.mock("$lib/api/client.js", () => ({ apiGet: vi.fn() }));

describe("NeighborPanel", () => {
  beforeEach(() => {
    vi.mocked(apiGet).mockResolvedValue({
      nodes: [
        { id: "current-note", title: "Current" },
        { id: "out-note", title: "Outbound" },
      ],
      links: [{ source: "current-note", target: "out-note" }],
    });
  });

  afterEach(() => {
    vi.mocked(apiGet).mockReset();
    vi.mocked(goto).mockReset();
    document.body.innerHTML = "";
  });

  function render(props = {}) {
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(NeighborPanel, {
      target,
      props: {
        vaultName: "main",
        data: {
          note_id: "current-note",
          outbound: [
            {
              note_id: "out-note",
              title: "Outbound Note",
              type: "wikilink",
              description: "Referenced directly",
            },
          ],
          semantic: [
            {
              note_id: "2026-05-08-related",
              title: "",
              type: "semantic",
              confidence: 0.876,
            },
          ],
          inbound: [
            {
              note_id: "in-note",
              title: "Inbound Note",
              type: "backlink",
            },
          ],
        },
        ...props,
      },
    });
    return { target, component };
  }

  it("renders neighbor groups, summaries, links, confidence, and the ego graph", async () => {
    const { target, component } = render();
    await Promise.resolve();
    await tick();

    expect(apiGet).toHaveBeenCalledWith(
      "/api/v1/vault/main/graph/ego/current-note",
    );
    expect(target.querySelector(".divider-label")?.textContent).toBe(
      "SIGNAL ANALYZER",
    );
    expect(
      [...target.querySelectorAll(".group-label")].map(
        (node) => node.textContent,
      ),
    ).toEqual(["OUTBOUND", "SEMANTIC", "INBOUND"]);

    const links = [
      ...target.querySelectorAll<HTMLAnchorElement>(".neighbor-link"),
    ];
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/main/notes/out-note",
      "/main/notes/2026-05-08-related",
      "/main/notes/in-note",
    ]);
    expect(target.textContent).toContain("Referenced directly");
    expect(target.textContent).toContain("2026-05-08");
    expect(target.textContent).toContain("backlink");
    expect(target.querySelector(".confidence")?.textContent).toBe("0.88");
    expect(
      target.querySelector(
        '[aria-label="Ego constellation — 2-hop note graph"]',
      ),
    ).not.toBeNull();

    target.querySelector<SVGGElement>(".ring-node")?.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Enter",
        bubbles: true,
      }),
    );
    expect(goto).toHaveBeenCalledWith("/main/notes/out-note");

    unmount(component);
  });

  it("does not render panel chrome while loading or when there are no groups", async () => {
    const loading = render({ loading: true });
    await tick();
    expect(loading.target.querySelector(".neighbor-panel")).toBeNull();
    unmount(loading.component);

    const empty = render({
      data: {
        note_id: "current-note",
        outbound: [],
        semantic: [],
        inbound: [],
      },
    });
    await tick();
    expect(empty.target.querySelector(".neighbor-panel")).toBeNull();
    unmount(empty.component);
  });
});
