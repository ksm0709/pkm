/**
 * Frontmatter byline widget — slice 4 / F4-3.
 *
 * A CM6 ViewPlugin that detects a YAML frontmatter block at the very start
 * of the document (delimited by `---\n` at offset 0 and a closing `---\n`)
 * and replaces it with a single italic Newsreader caption widget rendered
 * above the H1, e.g. "by {author} · {date}".
 *
 * Cursor-swap behavior (R5 mitigation):
 *   - When the cursor (selection head) is OUTSIDE the frontmatter range,
 *     the entire `---\n...\n---\n` block is replaced with a WidgetType.
 *   - When the cursor is INSIDE the range, no decoration is applied so the
 *     raw YAML is editable.
 *   - WidgetType.eq() returns true when the rendered caption text matches,
 *     so DOM is reused on cursor moves and only re-renders when content
 *     actually changes — avoids flicker.
 *
 * Lightweight YAML parsing only — `key: value` per-line regex. No external
 * YAML library; this widget renders a caption, not a full editor.
 */
import { EditorView, ViewPlugin, Decoration, WidgetType } from '@codemirror/view';
import { RangeSetBuilder } from '@codemirror/state';

// Match a key:value line inside the frontmatter block. Keys are simple
// identifiers (a-z, 0-9, _, -); values are everything to end of line.
const KV_RE = /^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$/;

/**
 * Locate the frontmatter range in the document.
 *
 * @param {import('@codemirror/state').Text} doc
 * @returns {{from:number,to:number,body:string}|null}
 */
function findFrontmatter(doc) {
  // Must start with "---\n" at the very beginning.
  if (doc.length < 8) return null;
  const head = doc.sliceString(0, 4);
  if (head !== '---\n') return null;

  // Search the document for the closing "\n---\n" or "\n---" at EOF.
  const text = doc.sliceString(0, Math.min(doc.length, 4096));
  // Look for a line that is exactly "---" after the opener.
  // Use a regex anchored on newline boundaries.
  const closeRe = /\n---(\n|$)/g;
  closeRe.lastIndex = 4; // skip past the opener
  const m = closeRe.exec(text);
  if (!m) return null;
  const closeStart = m.index + 1; // position of the "---" line start
  const closeEnd = closeStart + 3 + (m[1] === '\n' ? 1 : 0); // include trailing newline if present
  const body = text.slice(4, closeStart);
  return { from: 0, to: closeEnd, body };
}

/**
 * Parse `key: value` lines from a frontmatter body.
 *
 * @param {string} body
 * @returns {Record<string,string>}
 */
function parseFields(body) {
  /** @type {Record<string,string>} */
  const out = {};
  const lines = body.split('\n');
  for (const line of lines) {
    const m = KV_RE.exec(line);
    if (!m) continue;
    let v = m[2].trim();
    // Strip surrounding quotes.
    if (
      (v.startsWith('"') && v.endsWith('"')) ||
      (v.startsWith("'") && v.endsWith("'"))
    ) {
      v = v.slice(1, -1);
    }
    out[m[1]] = v;
  }
  return out;
}

/**
 * Build the caption text from parsed frontmatter fields.
 *
 * @param {Record<string,string>} fm
 * @returns {string}
 */
function buildCaption(fm) {
  const author = fm.author;
  const date = fm.date || fm.created || fm.updated;
  const parts = [];
  if (author) parts.push(`by ${author}`);
  if (date) parts.push(date);
  return parts.join(' · ');
}

class BylineWidget extends WidgetType {
  /** @param {string} caption */
  constructor(caption) {
    super();
    this.caption = caption;
  }
  /** @param {BylineWidget} other */
  eq(other) {
    return other.caption === this.caption;
  }
  toDOM() {
    const div = document.createElement('div');
    div.className = 'cm-frontmatter-byline';
    div.textContent = this.caption;
    return div;
  }
  ignoreEvent() {
    return false;
  }
}

/** @param {import('@codemirror/view').EditorView} view */
function buildDecorations(view) {
  /** @type {RangeSetBuilder<Decoration>} */
  const builder = new RangeSetBuilder();
  const fm = findFrontmatter(view.state.doc);
  if (!fm) return builder.finish();

  // If cursor is INSIDE the frontmatter range, render raw YAML (no deco).
  const head = view.state.selection.main.head;
  if (head >= fm.from && head <= fm.to) return builder.finish();

  const fields = parseFields(fm.body);
  const caption = buildCaption(fields);
  if (!caption) return builder.finish();

  builder.add(
    fm.from,
    fm.to,
    Decoration.replace({
      widget: new BylineWidget(caption),
      block: true
    })
  );
  return builder.finish();
}

export const frontmatterByline = ViewPlugin.fromClass(
  class {
    /** @param {import('@codemirror/view').EditorView} view */
    constructor(view) {
      /** @type {import('@codemirror/view').DecorationSet} */
      this.decorations = buildDecorations(view);
    }
    /** @param {import('@codemirror/view').ViewUpdate} update */
    update(update) {
      if (
        update.docChanged ||
        update.selectionSet ||
        update.viewportChanged
      ) {
        this.decorations = buildDecorations(update.view);
      }
    }
  },
  { decorations: (v) => v.decorations }
);

export const frontmatterBylineTheme = EditorView.baseTheme({
  '.cm-frontmatter-byline': {
    fontFamily: 'var(--font-display)',
    fontStyle: 'italic',
    color: 'var(--text-muted)',
    fontSize: 'var(--type-caption-size, 14px)',
    lineHeight: 'var(--type-caption-lh, 1.4)',
    marginBottom: 'var(--space-2, 8px)'
  }
});
