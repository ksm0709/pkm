// @vitest-environment jsdom
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { afterEach, describe, expect, it } from "vitest";
import { liveStyling, liveStylingTheme } from "./live-styling.js";

/** @type {EditorView[]} */
const views = [];

afterEach(() => {
  for (const view of views.splice(0)) view.destroy();
  document.body.innerHTML = "";
});

/**
 * @param {string} doc
 * @param {number} [selection]
 */
function createView(doc, selection = 0) {
  const parent = document.createElement("div");
  document.body.appendChild(parent);
  const view = new EditorView({
    parent,
    state: EditorState.create({
      doc,
      selection: { anchor: selection },
      extensions: [liveStyling, liveStylingTheme],
    }),
  });
  views.push(view);
  return view;
}

describe("live markdown styling", () => {
  it("styles inactive markdown lines while preserving the active line as raw editable text", () => {
    const view = createView(
      [
        "# Active **raw** [local](url)",
        "## Styled **bold** *italic* ~~gone~~ `code` [Link](note)",
        "> quoted body",
        "- bullet item",
        "---",
      ].join("\n"),
    );

    expect(view.dom.querySelector(".cm-line")?.textContent).toContain(
      "# Active **raw** [local](url)",
    );
    expect(view.dom.querySelector(".cm-md-h1")).toBeNull();

    expect(view.dom.querySelector(".cm-md-h2")?.textContent).toContain(
      "Styled",
    );
    expect(view.dom.querySelector(".cm-md-bold")?.textContent).toBe("bold");
    expect(view.dom.querySelector(".cm-md-italic")?.textContent).toBe("italic");
    expect(view.dom.querySelector(".cm-md-strike")?.textContent).toBe("gone");
    expect(view.dom.querySelector(".cm-md-code")?.textContent).toBe("code");
    expect(view.dom.querySelector(".cm-md-link")?.textContent).toBe("Link");
    expect(view.dom.querySelector(".cm-md-quote")?.textContent).toContain(
      "quoted body",
    );
    expect(view.dom.querySelector(".cm-md-bullet")?.textContent).toBe("• ");
    expect(view.dom.querySelector(".cm-md-hr")).not.toBeNull();
  });

  it("recomputes the raw cursor line when the selection moves", () => {
    const doc = "# Raw heading\n## Cursor destination\n";
    const view = createView(doc);
    const secondLine = doc.indexOf("## Cursor");

    expect(view.dom.querySelector(".cm-md-h1")).toBeNull();
    expect(view.dom.querySelector(".cm-md-h2")?.textContent).toContain(
      "Cursor destination",
    );

    view.dispatch({ selection: { anchor: secondLine } });

    expect(view.dom.querySelector(".cm-md-h1")?.textContent).toContain(
      "Raw heading",
    );
    expect(view.dom.querySelector(".cm-md-h2")).toBeNull();
    expect(view.dom.textContent).toContain("## Cursor destination");
  });
});
