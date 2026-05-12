/**
 * Live styling — basics only (slice 2 / F2-2).
 *
 * A CM6 ViewPlugin that renders cursor-line-reveal markdown:
 *   - Off-cursor lines are decorated (markers hidden, styled spans applied).
 *   - The active line (line containing the primary selection head) shows
 *     RAW markdown so the writer can edit it.
 *
 * Re-decorate on doc change AND on cursor move. NO Maximalist features
 * (no tables/math/footnotes/admonitions/wikilink/frontmatter widgets) —
 * those land in slice 4.
 */
import {
  EditorView,
  ViewPlugin,
  Decoration,
  WidgetType,
} from "@codemirror/view";
import { RangeSetBuilder } from "@codemirror/state";

// ---------- inline-marker matchers (single-line only) ----------

// Each entry: { regex, hide, mark }.
//   - hide: boolean — if true, replace the leading + trailing markers with
//           a zero-width Decoration.replace so the marker glyphs disappear.
//   - mark: CSS class applied to the inner content.
//
// IMPORTANT: regex must use a single capture group covering the inner text.
// Marker length is computed from match boundaries minus the captured span.
const INLINE_RULES = [
  { regex: /\*\*([^*\n]+)\*\*/g, hide: true, mark: "cm-md-bold", marker: 2 },
  {
    regex: /(?<!\*)\*([^*\n]+)\*(?!\*)/g,
    hide: true,
    mark: "cm-md-italic",
    marker: 1,
  },
  { regex: /~~([^~\n]+)~~/g, hide: true, mark: "cm-md-strike", marker: 2 },
  { regex: /`([^`\n]+)`/g, hide: true, mark: "cm-md-code", marker: 1 },
];

// Link matcher: [text](url) — hide brackets and the URL portion entirely.
const LINK_RE = /\[([^\]\n]+)\]\(([^)\n]+)\)/g;

// Block patterns (line-prefix).
const HEADING_RE = /^(#{1,3}) (.*)$/;
const QUOTE_RE = /^(> ?)(.*)$/;
const BULLET_RE = /^(\s*)([-*]) (.*)$/;
const HR_RE = /^---+\s*$/;

const HIDE = Decoration.replace({});

/** @param {number} level */
function lineHeadingClass(level) {
  return level === 1 ? "cm-md-h1" : level === 2 ? "cm-md-h2" : "cm-md-h3";
}

/** @param {import('@codemirror/view').EditorView} view */
function buildDecorations(view) {
  /** @type {RangeSetBuilder<Decoration>} */
  const builder = new RangeSetBuilder();
  const sel = view.state.selection.main;
  // Use the line containing the selection HEAD as the "active" line. If
  // the user has a multi-line selection, we still consider the head's
  // line the only raw line — ranges across multiple raw lines are an
  // edge case the user can resolve by collapsing the selection.
  const activeLine = view.state.doc.lineAt(sel.head).number;

  for (const { from, to } of view.visibleRanges) {
    let pos = from;
    while (pos <= to) {
      const line = view.state.doc.lineAt(pos);
      if (line.number !== activeLine) {
        decorateLine(builder, line);
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
function decorateLine(builder, line) {
  const text = line.text;

  // ----- block patterns -----
  let blockHandled = false;

  if (HR_RE.test(text)) {
    builder.add(
      line.from,
      line.from,
      Decoration.line({ attributes: { class: "cm-md-hr" } }),
    );
    blockHandled = true;
  } else {
    const h = HEADING_RE.exec(text);
    if (h) {
      const level = h[1].length;
      builder.add(
        line.from,
        line.from,
        Decoration.line({ attributes: { class: lineHeadingClass(level) } }),
      );
      // Hide "### " marker (level chars + 1 space).
      builder.add(line.from, line.from + level + 1, HIDE);
      blockHandled = true;
    } else {
      const q = QUOTE_RE.exec(text);
      if (q) {
        builder.add(
          line.from,
          line.from,
          Decoration.line({ attributes: { class: "cm-md-quote" } }),
        );
        builder.add(line.from, line.from + q[1].length, HIDE);
        blockHandled = true;
      } else {
        const b = BULLET_RE.exec(text);
        if (b) {
          const indent = b[1].length;
          // Hide "- " or "* " (2 chars) but keep indent.
          builder.add(
            line.from + indent,
            line.from + indent + 2,
            Decoration.replace({ widget: new BulletWidget() }),
          );
          blockHandled = true;
        }
      }
    }
  }

  if (blockHandled && HR_RE.test(text)) {
    // For HR, no inline scan needed.
    return;
  }

  // ----- inline scan (collect, sort, then add in order) -----
  /** @type {{from:number,to:number,deco:any}[]} */
  const ranges = [];

  for (const rule of INLINE_RULES) {
    rule.regex.lastIndex = 0;
    let m;
    while ((m = rule.regex.exec(text)) !== null) {
      const start = line.from + m.index;
      const end = start + m[0].length;
      const innerStart = start + rule.marker;
      const innerEnd = end - rule.marker;
      if (rule.hide) {
        ranges.push({ from: start, to: innerStart, deco: HIDE });
        ranges.push({ from: innerEnd, to: end, deco: HIDE });
      }
      ranges.push({
        from: innerStart,
        to: innerEnd,
        deco: Decoration.mark({ class: rule.mark }),
      });
    }
  }

  // Links: [text](url) — hide `[`, hide `](url)`, mark text as link.
  LINK_RE.lastIndex = 0;
  let lm;
  while ((lm = LINK_RE.exec(text)) !== null) {
    const start = line.from + lm.index;
    const end = start + lm[0].length;
    const textStart = start + 1; // after `[`
    const textEnd = textStart + lm[1].length;
    ranges.push({ from: start, to: textStart, deco: HIDE });
    ranges.push({ from: textEnd, to: end, deco: HIDE });
    ranges.push({
      from: textStart,
      to: textEnd,
      deco: Decoration.mark({ class: "cm-md-link" }),
    });
  }

  ranges.sort((a, b) => a.from - b.from || a.to - b.to);
  for (const r of ranges) {
    if (r.from === r.to) continue;
    builder.add(r.from, r.to, r.deco);
  }
}

// Bullet replacement widget — render a typographic bullet glyph.
class BulletWidget extends WidgetType {
  toDOM() {
    const span = document.createElement("span");
    span.textContent = "• ";
    span.className = "cm-md-bullet";
    return span;
  }
  eq() {
    return true;
  }
  ignoreEvent() {
    return false;
  }
}

// ---------- ViewPlugin ----------

export const liveStyling = ViewPlugin.fromClass(
  class {
    /** @param {import('@codemirror/view').EditorView} view */
    constructor(view) {
      /** @type {import('@codemirror/view').DecorationSet} */
      this.decorations = buildDecorations(view);
    }
    /** @param {import('@codemirror/view').ViewUpdate} update */
    update(update) {
      if (update.docChanged || update.viewportChanged || update.selectionSet) {
        this.decorations = buildDecorations(update.view);
      }
    }
  },
  { decorations: (v) => v.decorations },
);

// ---------- styling theme ----------
//
// Kept minimal — color only. Heavier typography (Newsreader display) is
// applied via the existing prose styles in the design tokens; here we
// just upsize headings and apply muted color to markers/quote.
export const liveStylingTheme = EditorView.baseTheme({
  ".cm-md-h1": {
    fontFamily: "var(--font-display)",
    fontSize: "var(--type-h1-size, 28px)",
    fontWeight: "var(--type-h1-weight, 600)",
    lineHeight: "var(--type-h1-lh, 1.20)",
  },
  ".cm-md-h2": {
    fontFamily: "var(--font-display)",
    fontSize: "var(--type-h2-size, 20px)",
    fontWeight: "var(--type-h2-weight, 600)",
    lineHeight: "var(--type-h2-lh, 1.30)",
  },
  ".cm-md-h3": {
    fontFamily: "var(--font-display)",
    fontSize: "var(--type-h3-size, 17px)",
    fontWeight: "var(--type-h3-weight, 600)",
    lineHeight: "var(--type-h3-lh, 1.35)",
  },
  ".cm-md-quote": {
    color: "var(--text-muted)",
    fontStyle: "italic",
    borderLeft: "2px solid var(--border)",
    paddingLeft: "var(--space-3, 12px)",
  },
  ".cm-md-hr": {
    borderTop: "1px solid var(--border)",
    color: "transparent",
  },
  ".cm-md-bold": { fontWeight: "600" },
  ".cm-md-italic": { fontStyle: "italic" },
  ".cm-md-strike": { textDecoration: "line-through" },
  ".cm-md-code": {
    fontFamily: "var(--font-mono)",
    backgroundColor: "var(--bg-elev)",
    padding: "0 4px",
  },
  ".cm-md-link": {
    color: "var(--accent)",
    textDecoration: "underline",
    textUnderlineOffset: "2px",
  },
  ".cm-md-bullet": {
    color: "var(--text-muted)",
  },
});
