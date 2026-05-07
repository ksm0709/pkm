import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  detectInlineTrigger,
  fetchInlineSuggestions,
} from "../inline-suggestions.js";
import { inlineCompletionSource } from "./inline-completions.js";

vi.mock("../inline-suggestions.js", () => ({
  detectInlineTrigger: vi.fn(),
  fetchInlineSuggestions: vi.fn(),
}));

function completionContext(text, pos = text.length) {
  return {
    pos,
    state: {
      doc: {
        toString: () => text,
      },
    },
  };
}

describe("inline completion source", () => {
  beforeEach(() => {
    vi.mocked(detectInlineTrigger).mockReset();
    vi.mocked(fetchInlineSuggestions).mockReset();
    vi.unstubAllGlobals();
  });

  it("does not open completions without an inline trigger", async () => {
    vi.mocked(detectInlineTrigger).mockReturnValueOnce(null);

    await expect(
      inlineCompletionSource(completionContext("plain text")),
    ).resolves.toBeNull();
    expect(fetchInlineSuggestions).not.toHaveBeenCalled();
  });

  it("does not fetch suggestions when the current route has no vault segment", async () => {
    const trigger = { kind: "tag", query: "pkm", from: 5, to: 9 };
    vi.stubGlobal("location", { pathname: "/" });
    vi.mocked(detectInlineTrigger).mockReturnValueOnce(trigger);

    await expect(
      inlineCompletionSource(completionContext("tag #pkm")),
    ).resolves.toBeNull();
    expect(fetchInlineSuggestions).not.toHaveBeenCalled();
  });

  it("maps note and tag suggestions to CodeMirror completion options", async () => {
    const trigger = { kind: "note", query: "pkm", from: 7, to: 12 };
    vi.stubGlobal("location", { pathname: "/work-vault/notes/current" });
    vi.mocked(detectInlineTrigger).mockReturnValueOnce(trigger);
    vi.mocked(fetchInlineSuggestions).mockResolvedValueOnce([
      {
        kind: "note",
        label: "pkm-plan",
        title: "PKM Plan",
        detail: "note",
        insert: "[[pkm-plan]]",
        score: 0,
      },
      {
        kind: "tag",
        label: "#pkm",
        title: "#pkm",
        detail: "12 notes",
        insert: "#pkm",
        score: 1,
      },
    ]);

    await expect(
      inlineCompletionSource(completionContext("Open [[pkm")),
    ).resolves.toEqual({
      from: 7,
      to: 10,
      filter: false,
      options: [
        {
          label: "pkm-plan",
          detail: "PKM Plan",
          type: "text",
          apply: "[[pkm-plan]]",
        },
        {
          label: "#pkm",
          detail: "12 notes",
          type: "keyword",
          apply: "#pkm",
        },
      ],
    });
    expect(fetchInlineSuggestions).toHaveBeenCalledWith("work-vault", trigger);
  });

  it("returns null when the server has no matching suggestions", async () => {
    const trigger = { kind: "tag", query: "missing", from: 0, to: 8 };
    vi.stubGlobal("location", { pathname: "/main" });
    vi.mocked(detectInlineTrigger).mockReturnValueOnce(trigger);
    vi.mocked(fetchInlineSuggestions).mockResolvedValueOnce([]);

    await expect(
      inlineCompletionSource(completionContext("#missing")),
    ).resolves.toBeNull();
  });
});
