import { describe, expect, it } from "vitest";
import { appNavPages } from "./app-nav";
import { cmdkCoreCommandShortcuts } from "./cmdk-command-shortcuts";

describe("app navigation contract", () => {
  it("keeps primary destinations in the command palette order users scan", () => {
    expect(appNavPages.map((page) => page.id)).toEqual([
      "notes",
      "tags",
      "graph",
      "logger",
      "daily",
      "configs",
    ]);
    expect(appNavPages.every((page) => page.label && page.commandLabel)).toBe(
      true,
    );
    expect(appNavPages.every((page) => page.commandShortcut)).toBe(true);
    expect(new Set(appNavPages.map((page) => page.commandShortcut)).size).toBe(
      appNavPages.length,
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
      logger: "/main/logger",
      daily: "/main/daily",
      configs: "/main/configs",
    });
  });

  it("keeps the retained CmdK command registry without Ask passthrough", () => {
    expect(
      cmdkCoreCommandShortcuts.map(({ id, shortcut }) => ({ id, shortcut })),
    ).toEqual([
      { id: "cmd:jump", shortcut: "/" },
      { id: "cmd:daily", shortcut: "y" },
      { id: "cmd:daily-subnote", shortcut: "s" },
      { id: "cmd:index-vault", shortcut: "i" },
      { id: "cmd:switch", shortcut: "v" },
      { id: "cmd:theme", shortcut: "h" },
    ]);
  });

  it("keeps every CmdK command on a unique Space leader shortcut", () => {
    const shortcuts = [
      ...cmdkCoreCommandShortcuts.map((command) => command.shortcut),
      ...appNavPages.map((page) => page.commandShortcut),
    ];

    expect(shortcuts.every(Boolean)).toBe(true);
    expect(new Set(shortcuts).size).toBe(shortcuts.length);
    expect(shortcuts).not.toContain("k");
  });
});
