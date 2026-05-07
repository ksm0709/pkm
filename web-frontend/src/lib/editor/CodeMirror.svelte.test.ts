// @vitest-environment jsdom
import { EditorState } from "@codemirror/state";
import { EditorView, ViewPlugin } from "@codemirror/view";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { detectInlineTrigger } from "$lib/inline-suggestions.js";
import CodeMirror from "./CodeMirror.svelte";

vi.mock("$lib/inline-suggestions.js", () => ({
  detectInlineTrigger: vi.fn(() => null),
}));

describe("CodeMirror", () => {
  afterEach(() => {
    vi.mocked(detectInlineTrigger).mockReset();
    document.body.innerHTML = "";
  });

  function render(props = {}) {
    const target = document.createElement("div");
    document.body.appendChild(target);
    let capturedView: EditorView | null = null;
    const captureView = ViewPlugin.fromClass(
      class {
        constructor(view: EditorView) {
          capturedView = view;
        }
      },
    );
    const component = mount(CodeMirror, {
      target,
      props: {
        doc: "Initial note",
        extensions: [captureView],
        ...props,
      },
    });
    return {
      target,
      component,
      get view() {
        return capturedView;
      },
    };
  }

  it("mounts an editor with the provided document and tears it down cleanly", async () => {
    const harness = render();
    await tick();

    expect(harness.target.querySelector(".cm-editor")).not.toBeNull();
    expect(harness.target.querySelector(".cm-content")?.textContent).toContain(
      "Initial note",
    );
    expect(harness.view?.state.doc.toString()).toBe("Initial note");

    unmount(harness.component);
    expect(harness.target.querySelector(".cm-editor")).toBeNull();
  });

  it("honors read-only mode while still rendering custom extensions", async () => {
    const harness = render({ readOnly: true });
    await tick();

    expect(harness.view?.state.facet(EditorState.readOnly)).toBe(true);
    expect(
      harness.target
        .querySelector(".cm-content")
        ?.getAttribute("contenteditable"),
    ).toBe("false");

    unmount(harness.component);
  });

  it("runs inline trigger detection when editor-originated text changes", async () => {
    vi.mocked(detectInlineTrigger).mockReturnValue({
      kind: "tag",
      query: "pk",
      from: 13,
      to: 16,
    });
    const harness = render();
    await tick();

    harness.view?.dispatch({
      changes: { from: "Initial note".length, insert: " #pk" },
      selection: { anchor: "Initial note #pk".length },
    });
    await tick();

    expect(detectInlineTrigger).toHaveBeenCalledWith(
      "Initial note #pk",
      "Initial note #pk".length,
    );

    unmount(harness.component);
  });
});
