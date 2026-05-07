import { describe, expect, it } from "vitest";
import { appNavPages } from "./app-nav";

describe("app navigation contract", () => {
  it("keeps primary destinations in the command palette order users scan", () => {
    expect(appNavPages.map((page) => page.id)).toEqual([
      "notes",
      "tags",
      "graph",
      "ask",
      "logger",
      "workflows",
      "daily",
      "configs",
    ]);
    expect(appNavPages.every((page) => page.label && page.commandLabel)).toBe(
      true,
    );
  });

  it("builds vault-scoped links for every top-level app destination", () => {
    const hrefs = Object.fromEntries(
      appNavPages.map((page) => [page.id, page.href("main")]),
    );

    expect(hrefs).toEqual({
      notes: "/main",
      tags: "/main/tags",
      graph: "/main/graph",
      ask: "/main/ask",
      logger: "/main/logger",
      workflows: "/main/workflows",
      daily: "/main/daily",
      configs: "/main/configs",
    });
  });
});
