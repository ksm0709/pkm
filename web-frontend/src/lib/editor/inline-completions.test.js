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

/**
 * @param {string} text
 * @param {number} [pos]
 * @returns {import("@codemirror/autocomplete").CompletionContext}
 */
function completionContext(text, pos = text.length) {
  return /** @type {import("@codemirror/autocomplete").CompletionContext} */ (
    /** @type {unknown} */ ({
      pos,
      state: {
        doc: {
          toString: () => text,
        },
      },
    })
  );
}

/**
 * @param {"note" | "tag"} kind
 * @param {string} query
 * @param {number} from
 * @param {number} to
 * @returns {import("../inline-suggestions.js").InlineTrigger}
 */
function inlineTrigger(kind, query, from, to) {
  return { kind, query, from, to };
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
    const trigger = inlineTrigger("tag", "pkm", 5, 9);
    vi.stubGlobal("location", { pathname: "/" });
    vi.mocked(detectInlineTrigger).mockReturnValueOnce(trigger);

    await expect(
      inlineCompletionSource(completionContext("tag #pkm")),
    ).resolves.toBeNull();
    expect(fetchInlineSuggestions).not.toHaveBeenCalled();
  });

  it("maps note and tag suggestions to CodeMirror completion options", async () => {
    const trigger = inlineTrigger("note", "pkm", 7, 12);
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
    const trigger = inlineTrigger("tag", "missing", 0, 8);
    vi.stubGlobal("location", { pathname: "/main" });
    vi.mocked(detectInlineTrigger).mockReturnValueOnce(trigger);
    vi.mocked(fetchInlineSuggestions).mockResolvedValueOnce([]);

    await expect(
      inlineCompletionSource(completionContext("#missing")),
    ).resolves.toBeNull();
  });
});
