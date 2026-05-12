import { describe, expect, it } from "vitest";
import { normalizeGraph } from "./normalize";

describe("normalizeGraph", () => {
  it("exposes confidence weight community hub radius and importance from enriched graph data", () => {
    const graph = normalizeGraph({
      nodes: [
        {
          id: "hub-pkm-development",
          title: "PKM Development",
          type: "note",
          graph_tier: "hub",
          community: "pkm",
        },
        {
          id: "project-plan",
          title: "Project Plan",
          type: "note",
          clusters: ["planning"],
        },
        { id: "tag:pkm", label: "pkm", type: "tag", top_tags: ["pkm"] },
      ],
      edges: [
        {
          source: "hub-pkm-development",
          target: "project-plan",
          type: "semantic_similar",
          confidence: 0.92,
          weight: 2.5,
        },
        { source: { id: "project-plan" }, target: "tag:pkm", type: "has_tag" },
      ],
    });

    expect(
      graph.nodes.find((node) => node.id === "hub-pkm-development"),
    ).toMatchObject({
      community: "pkm",
      degree: 1,
      hub: true,
      importance: 1,
      radius: expect.any(Number),
    });
    expect(
      graph.nodes.find((node) => node.id === "project-plan"),
    ).toMatchObject({
      community: "planning",
      degree: 2,
      hub: false,
    });
    expect(graph.nodes.find((node) => node.id === "tag:pkm")).toMatchObject({
      community: "pkm",
      type: "tag",
    });
    expect(graph.edges[0]).toMatchObject({
      confidence: 0.92,
      weight: 2.5,
    });
    expect(graph.edges[1]).toMatchObject({
      confidence: 0.5,
      weight: expect.any(Number),
    });
  });

  it("derives hub status from high normalized degree when graph tier is absent", () => {
    const graph = normalizeGraph({
      nodes: [
        { id: "center", title: "Center", type: "note" },
        { id: "a", title: "A", type: "note" },
        { id: "b", title: "B", type: "note" },
        { id: "c", title: "C", type: "note" },
        { id: "d", title: "D", type: "note" },
      ],
      links: [
        { source: "center", target: "a" },
        { source: "center", target: "b" },
        { source: "center", target: "c" },
        { source: "center", target: "d" },
      ],
    });

    const center = graph.nodes.find((node) => node.id === "center");
    const leaf = graph.nodes.find((node) => node.id === "a");

    expect(center?.hub).toBe(true);
    expect(center?.importance).toBeGreaterThan(leaf?.importance ?? 0);
    expect(center?.radius).toBeGreaterThan(leaf?.radius ?? 0);
  });
});
