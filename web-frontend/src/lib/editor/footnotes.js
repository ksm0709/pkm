/**
 * footnotes — F4-1 (Maximalist).
 *
 * Two recognisers:
 *   1. Inline reference `[^id]` — styled as superscript-ish accent link.
 *   2. Definition `[^id]: text` at line start — `[^id]:` marker faded.
 *
 * Cursor-line-reveal interop: on the active line, decorations are
 * suppressed so the writer sees raw markdown.
 */
import { ViewPlugin, Decoration, EditorView } from '@codemirror/view';
import { RangeSetBuilder } from '@codemirror/state';

const REF_RE = /\[\^([^\]\s]+)\]/g;
const DEF_RE = /^(\[\^([^\]\s]+)\]:)\s*(.*)$/;

/**
 * @param {import('@codemirror/view').EditorView} view
 */
function buildDecorations(view) {
  /** @type {RangeSetBuilder<Decoration>} */
  const builder = new RangeSetBuilder();
  const sel = view.state.selection.main;
  const activeLine = view.state.doc.lineAt(sel.head).number;

  for (const { from, to } of view.visibleRanges) {
    let pos = from;
    while (pos <= to) {
      const line = view.state.doc.lineAt(pos);
      if (line.number !== activeLine) {
        /** @type {{from:number,to:number,deco:any}[]} */
        const ranges = [];

        const def = DEF_RE.exec(line.text);
        if (def) {
          const markerLen = def[1].length;
          ranges.push({
            from: line.from,
            to: line.from + markerLen,
            deco: Decoration.mark({ class: 'cm-md-footnote-def-marker' })
          });
        }

        REF_RE.lastIndex = 0;
        let m;
        while ((m = REF_RE.exec(line.text)) !== null) {
          const start = line.from + m.index;
          const end = start + m[0].length;
          // Skip definition's own leading [^id]: marker.
          if (def && start < line.from + def[1].length) continue;
          ranges.push({
            from: start,
            to: end,
            deco: Decoration.mark({ class: 'cm-md-footnote-ref' })
          });
        }

        ranges.sort((a, b) => a.from - b.from || a.to - b.to);
        for (const r of ranges) {
          if (r.from === r.to) continue;
          builder.add(r.from, r.to, r.deco);
        }
      }
      pos = line.to + 1;
      if (line.to >= view.state.doc.length) break;
    }
  }
  return builder.finish();
}

export const footnotes = ViewPlugin.fromClass(
  class {
    /** @param {import('@codemirror/view').EditorView} view */
    constructor(view) {
      this.decorations = buildDecorations(view);
    }
    /** @param {import('@codemirror/view').ViewUpdate} update */
    update(update) {
      if (update.docChanged || update.viewportChanged || update.selectionSet) {
        this.decorations = buildDecorations(update.view);
      }
    }
  },
  { decorations: (v) => v.decorations }
);

export const footnotesTheme = EditorView.baseTheme({
  '.cm-md-footnote-ref': {
    color: 'var(--accent)',
    fontSize: '0.8em',
    verticalAlign: 'super',
    lineHeight: '1',
    textDecoration: 'underline',
    textUnderlineOffset: '2px'
  },
  '.cm-md-footnote-def-marker': {
    color: 'var(--text-faint)',
    fontFamily: 'var(--font-mono)'
  }
});
