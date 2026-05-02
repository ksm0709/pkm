/**
 * katex-lazy — F4-1 (Maximalist).
 *
 * CM6 ViewPlugin that scans visible ranges for `$$...$$` (block) and
 * `$...$` (inline) math delimiters. On the first match in the document,
 * it dynamically imports `katex` and its CSS, then renders each match
 * as a Decoration.replace widget.
 *
 * IMPORTANT: katex is imported via `import('katex')` ONLY — never as a
 * top-level import. This ensures the main bundle does not statically
 * include katex; it ships in its own chunk fetched on demand.
 *
 * Cursor-line-reveal interop: the active line is left raw so the user
 * can edit math source. Decorations only apply on non-active lines.
 */
import { ViewPlugin, Decoration, WidgetType, EditorView } from '@codemirror/view';
import { RangeSetBuilder } from '@codemirror/state';

let katexModule = null;
let katexLoading = null;
let cssInjected = false;

/**
 * Lazily fetch katex (JS + CSS). Returns a Promise that resolves to the
 * default export. Subsequent calls reuse the in-flight or completed
 * promise.
 */
function loadKatex() {
  if (katexModule) return Promise.resolve(katexModule);
  if (katexLoading) return katexLoading;
  katexLoading = (async () => {
    const mod = await import('katex');
    if (!cssInjected && typeof document !== 'undefined') {
      // Vite resolves the `?url` query at build time, emitting katex CSS
      // as a separate asset and returning the URL. We attach it via a
      // <link> tag so it doesn't bloat the main JS bundle.
      try {
        // @ts-ignore — Vite-specific query suffix
        const mod = await import('katex/dist/katex.min.css?url');
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = mod.default;
        document.head.appendChild(link);
      } catch {
        // ignore — math will render unstyled but visible.
      }
      cssInjected = true;
    }
    katexModule = mod.default ?? mod;
    return katexModule;
  })();
  return katexLoading;
}

class MathWidget extends WidgetType {
  /**
   * @param {string} source
   * @param {boolean} display
   */
  constructor(source, display) {
    super();
    this.source = source;
    this.display = display;
  }
  eq(other) {
    return other.source === this.source && other.display === this.display;
  }
  toDOM() {
    const host = document.createElement('span');
    host.className = this.display ? 'cm-md-math cm-md-math-block' : 'cm-md-math';
    if (katexModule) {
      try {
        katexModule.render(this.source, host, {
          throwOnError: false,
          displayMode: this.display
        });
      } catch {
        host.textContent = this.source;
      }
    } else {
      host.textContent = this.source;
    }
    return host;
  }
  ignoreEvent() {
    return false;
  }
}

// Block: `$$...$$` may span multiple lines but in this slice we only
// support the single-line form. Inline: `$...$` single line.
const BLOCK_RE = /\$\$([^$\n]+)\$\$/g;
const INLINE_RE = /(?<!\$)\$([^$\n]+)\$(?!\$)/g;

/**
 * @param {import('@codemirror/view').EditorView} view
 */
function buildDecorations(view) {
  /** @type {RangeSetBuilder<Decoration>} */
  const builder = new RangeSetBuilder();
  const sel = view.state.selection.main;
  const activeLine = view.state.doc.lineAt(sel.head).number;
  let foundAny = false;

  for (const { from, to } of view.visibleRanges) {
    let pos = from;
    while (pos <= to) {
      const line = view.state.doc.lineAt(pos);
      if (line.number !== activeLine) {
        /** @type {{from:number,to:number,deco:any}[]} */
        const ranges = [];

        BLOCK_RE.lastIndex = 0;
        let bm;
        while ((bm = BLOCK_RE.exec(line.text)) !== null) {
          foundAny = true;
          const start = line.from + bm.index;
          const end = start + bm[0].length;
          ranges.push({
            from: start,
            to: end,
            deco: Decoration.replace({ widget: new MathWidget(bm[1], true) })
          });
        }

        INLINE_RE.lastIndex = 0;
        let im;
        while ((im = INLINE_RE.exec(line.text)) !== null) {
          // Skip if overlaps an already-claimed block range.
          const start = line.from + im.index;
          const end = start + im[0].length;
          const overlaps = ranges.some((r) => start < r.to && end > r.from);
          if (overlaps) continue;
          foundAny = true;
          ranges.push({
            from: start,
            to: end,
            deco: Decoration.replace({ widget: new MathWidget(im[1], false) })
          });
        }

        ranges.sort((a, b) => a.from - b.from);
        for (const r of ranges) builder.add(r.from, r.to, r.deco);
      }
      pos = line.to + 1;
      if (line.to >= view.state.doc.length) break;
    }
  }
  return { decorations: builder.finish(), foundAny };
}

export const katexLazy = ViewPlugin.fromClass(
  class {
    /** @param {import('@codemirror/view').EditorView} view */
    constructor(view) {
      const { decorations, foundAny } = buildDecorations(view);
      this.decorations = decorations;
      if (foundAny) this._kickLoad(view);
    }
    /** @param {import('@codemirror/view').ViewUpdate} update */
    update(update) {
      if (update.docChanged || update.viewportChanged || update.selectionSet) {
        const { decorations, foundAny } = buildDecorations(update.view);
        this.decorations = decorations;
        if (foundAny && !katexModule) this._kickLoad(update.view);
      }
    }
    _kickLoad(view) {
      loadKatex().then(() => {
        // Re-render once katex is ready by dispatching a no-op effect.
        view.dispatch({});
      });
    }
  },
  { decorations: (v) => v.decorations }
);

export const katexLazyTheme = EditorView.baseTheme({
  '.cm-md-math': {
    fontFamily: 'var(--font-display)',
    color: 'var(--text)',
    padding: '0 2px'
  },
  '.cm-md-math-block': {
    display: 'inline-block',
    padding: '0 var(--space-3, 12px)'
  }
});
