/**
 * Tag and relation marker rendering — F4-5.
 *
 * A CM6 ViewPlugin that decorates `#tag` tokens as small rounded pills and
 * `&relation` tokens as square chips. Cursor-line-reveal: the active line
 * shows the raw marker; off-cursor lines render the chip.
 *
 * Tag regex: `#[a-zA-Z0-9_/-]+`. We avoid matches preceded by an
 * alphanumeric char so `foo#bar` and inline anchors don't trip.
 */
import { EditorView, ViewPlugin, Decoration } from "@codemirror/view";
import { RangeSetBuilder } from "@codemirror/state";

const TAG_RE = /(^|[^a-zA-Z0-9_/-])(#[a-zA-Z0-9_/-]+)/g;
const RELATION_RE = /(^|[^a-zA-Z0-9_&/-])(&[a-zA-Z][a-zA-Z0-9_-]*)/g;
const HIDE = Decoration.replace({});

/** @param {import('@codemirror/view').EditorView} view */
function buildTagDecorations(view) {
  /** @type {RangeSetBuilder<Decoration>} */
  const builder = new RangeSetBuilder();
  const sel = view.state.selection.main;
  const activeLine = view.state.doc.lineAt(sel.head).number;

  for (const { from, to } of view.visibleRanges) {
    let pos = from;
    while (pos <= to) {
      const line = view.state.doc.lineAt(pos);
      if (line.number !== activeLine) {
        decorateInlineChipsInLine(builder, line);
      }
      pos = line.to + 1;
      if (line.to >= view.state.doc.length) break;
    }
  }
  return builder.finish();
}

/**
 * @param {RangeSetBuilder<Decoration>} builder
 * @param {{from:number,to:number,text:string,number:number}} line
 */
function decorateInlineChipsInLine(builder, line) {
  const ranges = [];

  TAG_RE.lastIndex = 0;
  let m;
  while ((m = TAG_RE.exec(line.text)) !== null) {
    const tagStartInLine = m.index + m[1].length;
    const start = line.from + tagStartInLine;
    const end = start + m[2].length; // includes leading '#'
    // Hide the '#' marker.
    ranges.push({ from: start, to: start + 1, deco: HIDE });
    // Pill mark covers the tag name (after '#').
    ranges.push({
      from: start + 1,
      to: end,
      deco: Decoration.mark({ class: "cm-md-tag" }),
    });
  }

  RELATION_RE.lastIndex = 0;
  while ((m = RELATION_RE.exec(line.text)) !== null) {
    const relationStartInLine = m.index + m[1].length;
    const start = line.from + relationStartInLine;
    const end = start + m[2].length; // includes leading '&'
    ranges.push({ from: start, to: start + 1, deco: HIDE });
    ranges.push({
      from: start + 1,
      to: end,
      deco: Decoration.mark({ class: "cm-md-relation" }),
    });
  }

  ranges.sort((a, b) => a.from - b.from || a.to - b.to);
  for (const r of ranges) {
    if (r.from === r.to) continue;
    builder.add(r.from, r.to, r.deco);
  }
}

export const tagPill = ViewPlugin.fromClass(
  class {
    /** @param {import('@codemirror/view').EditorView} view */
    constructor(view) {
      /** @type {import('@codemirror/view').DecorationSet} */
      this.decorations = buildTagDecorations(view);
    }
    /** @param {import('@codemirror/view').ViewUpdate} update */
    update(update) {
      if (update.docChanged || update.viewportChanged || update.selectionSet) {
        this.decorations = buildTagDecorations(update.view);
      }
    }
  },
  { decorations: (v) => v.decorations },
);

export const tagPillTheme = EditorView.baseTheme({
  ".cm-md-tag": {
    fontFamily: "var(--font-mono)",
    fontSize: "0.85em",
    color: "var(--text-muted)",
    backgroundColor: "var(--bg-elev)",
    borderRadius: "4px",
    padding: "0 6px",
    marginRight: "2px",
  },
  ".cm-md-relation": {
    fontFamily: "var(--font-mono)",
    fontSize: "0.82em",
    color: "color-mix(in srgb, var(--accent) 74%, var(--text) 26%)",
    backgroundColor:
      "color-mix(in srgb, var(--accent) 13%, var(--surface-raised, var(--bg)))",
    border: "1px solid color-mix(in srgb, var(--accent) 46%, var(--border))",
    borderRadius: "2px",
    padding: "0 6px",
    marginRight: "2px",
    fontWeight: "700",
  },
  ".cm-md-relation::before": {
    content: '"&"',
  },
});
