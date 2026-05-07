// @vitest-environment jsdom
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.js";
import { slashCommandItems, slashSource } from "./slash-commands.js";

vi.mock("../api/client.js", () => ({ apiClient: vi.fn() }));

/** @type {EditorView[]} */
const views = [];

beforeEach(() => {
  window.history.pushState({}, "", "/main/notes/current");
});

afterEach(() => {
  for (const view of views.splice(0)) view.destroy();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.mocked(apiClient).mockReset();
  document.body.innerHTML = "";
});

function createView(doc) {
  const parent = document.createElement("div");
  document.body.appendChild(parent);
  const view = new EditorView({
    parent,
    state: EditorState.create({ doc }),
  });
  views.push(view);
  return view;
}

function command(label) {
  const item = slashCommandItems.find((candidate) => candidate.label === label);
  if (!item) throw new Error(`Missing slash command ${label}`);
  return item;
}

describe("slash command completions", () => {
  it("offers slash commands only from the start of the current line", () => {
    const matching = EditorState.create({ doc: "/su" });
    const result = slashSource({ state: matching, pos: 3 });

    expect(result).toMatchObject({
      from: 0,
      to: 3,
      validFor: /^\/\w*$/,
    });
    expect(result?.options.map((option) => option.label)).toEqual([
      "/subnote",
      "/daily",
      "/note",
      "/link",
      "/tag",
    ]);

    const embedded = EditorState.create({ doc: "body /su" });
    expect(slashSource({ state: embedded, pos: "body /su".length })).toBeNull();
  });

  it("inserts daily, note, link, and tag templates with editing selections", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-05-08T12:00:00.000Z"));

    const daily = createView("/");
    command("/daily").apply(daily, null, 0, 1);
    expect(daily.state.doc.toString()).toBe("[[2026-05-08]]");
    expect(daily.state.selection.main.anchor).toBe("[[2026-05-08]]".length);

    const note = createView("/");
    command("/note").apply(note, null, 0, 1);
    expect(note.state.doc.toString()).toBe("[[note-id]]");
    expect(
      note.state.sliceDoc(
        note.state.selection.main.from,
        note.state.selection.main.to,
      ),
    ).toBe("note-id");

    const link = createView("/");
    command("/link").apply(link, null, 0, 1);
    expect(link.state.doc.toString()).toBe("[text](url)");
    expect(
      link.state.sliceDoc(
        link.state.selection.main.from,
        link.state.selection.main.to,
      ),
    ).toBe("text");

    const tag = createView("/");
    command("/tag").apply(tag, null, 0, 1);
    expect(tag.state.doc.toString()).toBe("#tag");
    expect(
      tag.state.sliceDoc(
        tag.state.selection.main.from,
        tag.state.selection.main.to,
      ),
    ).toBe("tag");
  });

  it("creates a daily subnote and replaces the trigger with the returned wikilink", async () => {
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "Meeting notes"),
    );
    vi.mocked(apiClient).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ note_id: "2026-05-08-meeting-notes" }),
    });
    const view = createView("/subnote");

    await command("/subnote").apply(view, null, 0, "/subnote".length);

    expect(apiClient).toHaveBeenCalledWith("/api/v1/vault/main/daily/today", {
      method: "POST",
      body: JSON.stringify({
        type: "subnote",
        title: "Meeting notes",
        content: "",
      }),
    });
    expect(view.state.doc.toString()).toBe("[[2026-05-08-meeting-notes]]");
  });

  it("removes the slash trigger when subnote creation is cancelled or fails", async () => {
    vi.stubGlobal(
      "prompt",
      vi.fn(() => ""),
    );
    const cancelled = createView("/subnote");

    await command("/subnote").apply(cancelled, null, 0, "/subnote".length);

    expect(cancelled.state.doc.toString()).toBe("");
    expect(apiClient).not.toHaveBeenCalled();

    vi.stubGlobal(
      "prompt",
      vi.fn(() => "Broken"),
    );
    vi.stubGlobal("console", { ...console, error: vi.fn() });
    vi.mocked(apiClient).mockResolvedValue({ ok: false, status: 500 });
    const failed = createView("/subnote");

    await command("/subnote").apply(failed, null, 0, "/subnote".length);

    expect(failed.state.doc.toString()).toBe("");
    expect(console.error).toHaveBeenCalledWith(
      "subnote create failed:",
      expect.any(Error),
    );
  });
});
