import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiGet } from "./api/client.js";
import {
  applyInlineSuggestion,
  detectInlineTrigger,
  fetchInlineSuggestions,
} from "./inline-suggestions.js";

vi.mock("./api/client.js", () => ({ apiGet: vi.fn() }));

describe("inline suggestions", () => {
  beforeEach(() => {
    vi.mocked(apiGet).mockReset();
  });

  it("detects wikilink triggers at the cursor and keeps replacement bounds local", () => {
    const value = "Connect [[project pla with trailing text";
    const cursor = "Connect [[project pla".length;

    expect(detectInlineTrigger(value, cursor)).toEqual({
      kind: "note",
      query: "project pla",
      from: "Connect ".length,
      to: cursor,
    });
  });

  it("detects tag triggers only after a boundary", () => {
    expect(detectInlineTrigger("tags #pkm/work")).toEqual({
      kind: "tag",
      query: "pkm/work",
      from: "tags ".length,
      to: "tags #pkm/work".length,
    });
    expect(detectInlineTrigger("email#pkm")).toBeNull();
  });

  it("loads recent notes for an empty wikilink query and removes unusable rows", async () => {
    vi.mocked(apiGet).mockResolvedValueOnce([
      {
        note_id: "daily-review",
        title: "Daily Review",
        path: "notes/daily.md",
      },
      { title: "Inbox Zero", description: "workflow" },
      { note_id: "", title: "", path: "broken.md" },
      { note_id: "third", title: "Third" },
      { note_id: "fourth", title: "Fourth" },
      { note_id: "fifth", title: "Fifth" },
      { note_id: "sixth", title: "Sixth" },
      { note_id: "seventh", title: "Seventh" },
      { note_id: "eighth", title: "Eighth" },
      { note_id: "ninth", title: "Ninth" },
    ]);

    const suggestions = await fetchInlineSuggestions("work vault", {
      kind: "note",
      query: "",
      from: 0,
      to: 2,
    });

    expect(apiGet).toHaveBeenCalledWith("/api/v1/vault/work%20vault/notes");
    expect(suggestions).toHaveLength(8);
    expect(suggestions[0]).toMatchObject({
      kind: "note",
      label: "daily-review",
      title: "Daily Review",
      detail: "notes/daily.md",
      insert: "[[daily-review]]",
    });
    expect(suggestions[1]).toMatchObject({
      label: "Inbox Zero",
      insert: "[[Inbox Zero]]",
    });
    expect(suggestions.map((item) => item.label)).not.toContain("");
  });

  it("searches notes for a non-empty wikilink query and ranks exact and prefix matches first", async () => {
    vi.mocked(apiGet).mockResolvedValueOnce({
      results: [
        { note_id: "archive-pkm-plan", title: "Archive" },
        { note_id: "pkm", title: "PKM" },
        { note_id: "pkm-system", title: "PKM System" },
      ],
    });

    const suggestions = await fetchInlineSuggestions("main", {
      kind: "note",
      query: "pkm",
      from: 5,
      to: 10,
    });

    expect(apiGet).toHaveBeenCalledWith("/api/v1/vault/main/search?q=pkm");
    expect(suggestions.map((item) => item.label)).toEqual([
      "pkm",
      "pkm-system",
      "archive-pkm-plan",
    ]);
  });

  it("loads tags, formats note counts, filters blanks, ranks matches, and caps rows", async () => {
    vi.mocked(apiGet).mockResolvedValueOnce({
      tags: [
        { tag: "idea/archive", count: 9 },
        { tag: "idea", count: 1 },
        { tag: "", count: 12 },
        { tag: "project/idea", count: 2 },
        { tag: "idea-0", count: 1 },
        { tag: "idea-1", count: 1 },
        { tag: "idea-2", count: 1 },
        { tag: "idea-3", count: 1 },
        { tag: "idea-4", count: 1 },
        { tag: "other", count: 1 },
      ],
    });

    const suggestions = await fetchInlineSuggestions("main", {
      kind: "tag",
      query: "idea",
      from: 0,
      to: 5,
    });

    expect(apiGet).toHaveBeenCalledWith("/api/v1/vault/main/tags");
    expect(suggestions).toHaveLength(8);
    expect(suggestions.slice(0, 3).map((item) => item.label)).toEqual([
      "#idea",
      "#idea/archive",
      "#idea-0",
    ]);
    expect(suggestions.map((item) => item.label)).toContain("#project/idea");
    expect(suggestions[0]).toMatchObject({
      detail: "1 note",
      insert: "#idea",
    });
    expect(suggestions[1].detail).toBe("9 notes");
    expect(suggestions.map((item) => item.label)).not.toContain("#");
  });

  it("applies the selected suggestion without rewriting surrounding text", () => {
    const result = applyInlineSuggestion(
      "Before [[pk after",
      { kind: "note", query: "pk", from: 7, to: 11 },
      {
        kind: "note",
        label: "pkm-plan",
        title: "PKM Plan",
        detail: "note",
        insert: "[[pkm-plan]]",
        score: 0,
      },
    );

    expect(result).toEqual({
      value: "Before [[pkm-plan]] after",
      cursor: "Before [[pkm-plan]]".length,
    });
  });
});
