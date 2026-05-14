// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  GraphKeyNavigationState,
  graphKeyNav,
  noteHref,
} from "./graph-keynav.svelte";

function installSessionStorage() {
  const store = new Map<string, string>();
  vi.stubGlobal("sessionStorage", {
    getItem: vi.fn((key: string) => store.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => store.set(key, value)),
    removeItem: vi.fn((key: string) => store.delete(key)),
  });
}

describe("GraphKeyNavigationState", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    installSessionStorage();
    graphKeyNav.resetForTests();
  });

  it("ranks semantic candidates by confidence, title, then id", () => {
    const nav = new GraphKeyNavigationState();

    nav.setCurrentNoteNavigationContext("main", "source", [
      { note_id: "third", title: "Third", confidence: 0.7 },
      { note_id: "beta", title: "Beta", confidence: 0.9 },
      { note_id: "alpha", title: "Alpha", confidence: 0.9 },
    ]);

    expect(nav.rankedSemanticNeighbors.map((item) => item.note_id)).toEqual([
      "alpha",
      "beta",
      "third",
    ]);
    expect(nav.semanticRankActions.map((item) => item.key)).toEqual([
      "1",
      "2",
      "3",
    ]);
    expect(nav.semanticRankActions[0].description).toContain("Alpha");
    expect(nav.semanticRankActions[0].description).toContain("0.90");
  });

  it("pushes the current note before numeric semantic navigation", () => {
    const nav = new GraphKeyNavigationState();
    nav.setCurrentNoteNavigationContext("main", "source", [
      { note_id: "alpha", title: "Alpha", confidence: 0.9 },
    ]);

    expect(nav.navigateToSemanticRank(1)).toEqual({
      vaultName: "main",
      noteId: "alpha",
    });
    expect(nav.popNavigationStack()).toEqual({
      vaultName: "main",
      noteId: "source",
    });
  });

  it("supports next, previous, and persisted back-stack navigation", () => {
    const nav = new GraphKeyNavigationState();
    nav.setCurrentNoteNavigationContext("main", "source", [
      { note_id: "alpha", title: "Alpha", confidence: 0.9 },
      { note_id: "beta", title: "Beta", confidence: 0.8 },
    ]);

    expect(nav.navigateNextSemantic()).toEqual({
      vaultName: "main",
      noteId: "alpha",
    });
    nav.setCurrentNoteNavigationContext("main", "alpha", [
      { note_id: "source", title: "Source", confidence: 0.9 },
      { note_id: "beta", title: "Beta", confidence: 0.8 },
    ]);
    expect(nav.navigatePreviousSemantic()).toEqual({
      vaultName: "main",
      noteId: "beta",
    });

    const rehydrated = new GraphKeyNavigationState();
    expect(rehydrated.popNavigationStack("main")).toEqual({
      vaultName: "main",
      noteId: "alpha",
    });
  });

  it("builds encoded note hrefs", () => {
    expect(
      noteHref({ vaultName: "main vault", noteId: "2026-04-14-[주식분석]" }),
    ).toBe(
      "/main%20vault/notes/2026-04-14-%5B%EC%A3%BC%EC%8B%9D%EB%B6%84%EC%84%9D%5D",
    );
  });
});
