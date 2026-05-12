import { describe, expect, it } from "vitest";
import {
  graphNodeIsInteractive,
  graphNoteHref,
  isNavigableGraphNoteNode,
} from "./navigation";

describe("graph navigation", () => {
  it("builds encoded note links only for concrete note nodes", () => {
    expect(
      graphNoteHref("bear vault", { id: "daily note", type: "note" }),
    ).toBe("/bear%20vault/notes/daily%20note");
    expect(isNavigableGraphNoteNode({ id: "daily note", type: "note" })).toBe(
      true,
    );
    expect(graphNodeIsInteractive({ id: "daily note", type: "note" })).toBe(
      true,
    );
  });

  it("keeps tags and unresolved graph nodes inert", () => {
    expect(graphNoteHref("bear", { id: "tag:TODO", type: "tag" })).toBeNull();
    expect(
      graphNoteHref("bear", { id: "missing-note", type: "note_or_unresolved" }),
    ).toBeNull();
    expect(graphNodeIsInteractive({ id: "tag:TODO", type: "tag" })).toBe(false);
    expect(
      graphNodeIsInteractive({
        id: "missing-note",
        type: "note_or_unresolved",
      }),
    ).toBe(false);
  });

  it("rejects empty or malformed note ids", () => {
    expect(graphNoteHref("bear", { id: "", type: "note" })).toBeNull();
    expect(graphNoteHref("bear", { id: "   ", type: "note" })).toBeNull();
    expect(graphNoteHref("bear", null)).toBeNull();
  });
});
