// @vitest-environment jsdom
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { afterEach, describe, expect, it } from "vitest";
import { admonitions, admonitionsTheme } from "./admonitions.js";
import { checkboxes, checkboxesTheme } from "./checkboxes.js";
import { footnotes, footnotesTheme } from "./footnotes.js";
import {
  frontmatterByline,
  frontmatterBylineTheme,
} from "./frontmatter-byline.js";
import { katexLazy, katexLazyTheme } from "./katex-lazy.js";
import { markdownWithGfm } from "./markdown-extensions.js";
import { tagPill, tagPillTheme } from "./tag-pill.js";
import { pkmTheme } from "./theme.js";

/** @type {EditorView[]} */
const views = [];

afterEach(() => {
  for (const view of views.splice(0)) view.destroy();
  document.body.innerHTML = "";
});

function createView(doc, extensions, selection = 0) {
  const parent = document.createElement("div");
  document.body.appendChild(parent);
  const view = new EditorView({
    parent,
    state: EditorState.create({
      doc,
      selection: { anchor: selection },
      extensions,
    }),
  });
  views.push(view);
  return view;
}

describe("editor markdown decorations", () => {
  it("renders off-line tags as pills while leaving active-line and inline-anchor text raw", () => {
    const view = createView("active #skip\nbody #pkm and foo#bar\n", [
      tagPill,
      tagPillTheme,
    ]);

    const tagLabels = [...view.dom.querySelectorAll(".cm-md-tag")].map(
      (node) => node.textContent,
    );

    expect(tagLabels).toEqual(["pkm"]);
    expect(view.dom.textContent).toContain("#skip");
    expect(view.dom.textContent).toContain("foo#bar");
  });

  it("renders off-line relation vocabulary markers as square chips", () => {
    const view = createView(
      "active &source [[raw]]\nbody &depends_on [[target]] and foo&bar\n",
      [tagPill, tagPillTheme],
    );

    const relationLabels = [
      ...view.dom.querySelectorAll(".cm-md-relation"),
    ].map((node) => node.textContent);

    expect(relationLabels).toEqual(["depends_on"]);
    expect(view.dom.textContent).toContain("&source");
    expect(view.dom.textContent).toContain("foo&bar");
  });

  it("decorates off-line footnote references and definition markers without hiding active-line markdown", () => {
    const view = createView(
      "active [^skip]\nBody [^ref]\n[^def]: note with [^inside]\n",
      [footnotes, footnotesTheme],
    );

    const refs = [...view.dom.querySelectorAll(".cm-md-footnote-ref")].map(
      (node) => node.textContent,
    );
    const markers = [
      ...view.dom.querySelectorAll(".cm-md-footnote-def-marker"),
    ].map((node) => node.textContent);

    expect(refs).toEqual(["[^ref]", "[^inside]"]);
    expect(markers).toEqual(["[^def]:"]);
    expect(view.dom.textContent).toContain("[^skip]");
  });

  it("renders off-line admonition callouts as labels while preserving the active marker", () => {
    const view = createView(
      "> [!note] Active\n> body\n> [!warning] Careful\n> warning body\n",
      [admonitions, admonitionsTheme],
    );

    const labels = [...view.dom.querySelectorAll(".cm-md-admon-label")].map(
      (node) => node.textContent,
    );
    const warningLines = view.dom.querySelectorAll(".cm-md-admon-warning");

    expect(labels).toEqual(["!Warning: Careful"]);
    expect(warningLines.length).toBeGreaterThanOrEqual(2);
    expect(view.dom.textContent).toContain("> [!note] Active");
  });

  it("renders off-line task checkboxes and toggles the backing markdown", () => {
    const view = createView("- [ ] active\n- [ ] todo\n- [x] done\n", [
      checkboxes,
      checkboxesTheme,
    ]);

    const inputs = [...view.dom.querySelectorAll("input.cm-md-checkbox")];
    expect(inputs.map((input) => input.checked)).toEqual([false, true]);

    inputs[0].dispatchEvent(
      new MouseEvent("mousedown", {
        bubbles: true,
        cancelable: true,
      }),
    );

    expect(view.state.doc.toString()).toBe(
      "- [ ] active\n- [x] todo\n- [x] done\n",
    );
  });

  it("combines markdown GFM parsing with the pkm editor theme as editor extensions", () => {
    const view = createView("| A | B |\n| - | - |\n| 1 | 2 |\n", [
      markdownWithGfm,
      pkmTheme,
    ]);

    expect(view.state.facet(EditorState.languageData).length).toBeGreaterThan(
      0,
    );
    expect(view.dom.className).toContain("cm-editor");
  });

  it("renders frontmatter as an author/date byline only when the cursor is outside YAML", () => {
    const doc = '---\nauthor: "Ada"\ndate: 2026-05-08\n---\n# Title\n';
    const hidden = createView(
      doc,
      [frontmatterByline, frontmatterBylineTheme],
      doc.length,
    );

    expect(
      hidden.dom.querySelector(".cm-frontmatter-byline")?.textContent,
    ).toBe("by Ada · 2026-05-08");
    expect(hidden.dom.textContent).not.toContain("author:");

    const editable = createView(
      doc,
      [frontmatterByline, frontmatterBylineTheme],
      4,
    );
    expect(editable.dom.querySelector(".cm-frontmatter-byline")).toBeNull();
    expect(editable.dom.textContent).toContain("author:");
  });

  it("replaces off-line inline and block math while keeping active-line math editable", () => {
    const view = createView("active $raw$\nmath $x + y$ and $$z^2$$\n", [
      katexLazy,
      katexLazyTheme,
    ]);

    const math = [...view.dom.querySelectorAll(".cm-md-math")].map((node) =>
      node.textContent?.trim(),
    );

    expect(math).toEqual(["x + y", "z^2"]);
    expect(view.dom.textContent).toContain("$raw$");
  });
});
