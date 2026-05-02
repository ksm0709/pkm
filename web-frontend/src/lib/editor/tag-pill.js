/**
 * Tag pill rendering — F4-5.
 *
 * A CM6 ViewPlugin that decorates `#tag` tokens as small rounded pills.
 * Cursor-line-reveal: the active line shows the raw `#tag`; off-cursor
 * lines render the pill (the `#` marker is hidden via Decoration.replace
 * and the tag name is wrapped in a styled mark).
 *
 * Tag regex: `#[a-zA-Z0-9_/-]+`. We avoid matches preceded by an
 * alphanumeric char so `foo#bar` and inline anchors don't trip.
 */
import { EditorView, ViewPlugin, Decoration } from '@codemirror/view';
import { RangeSetBuilder } from '@codemirror/state';

const TAG_RE = /(^|[^a-zA-Z0-9_/-])(#[a-zA-Z0-9_/-]+)/g;
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
        decorateTagsInLine(builder, line);
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
function decorateTagsInLine(builder, line) {
  TAG_RE.lastIndex = 0;
  const ranges = [];
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
      deco: Decoration.mark({ class: 'cm-md-tag' })
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
      if (
        update.docChanged ||
        update.viewportChanged ||
        update.selectionSet
      ) {
        this.decorations = buildTagDecorations(update.view);
      }
    }
  },
  { decorations: (v) => v.decorations }
);

export const tagPillTheme = EditorView.baseTheme({
  '.cm-md-tag': {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.85em',
    color: 'var(--text-muted)',
    backgroundColor: 'var(--bg-elev)',
    borderRadius: '4px',
    padding: '0 6px',
    marginRight: '2px'
  }
});
